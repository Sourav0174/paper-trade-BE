"""
Mentor Service Orchestration Layer.

Orchestrates trade loading, FIFO position reconstruction, analytics calculations,
rule evaluations, insight prioritization, response generation, and review persistence.
"""

from datetime import datetime, timezone
import json
import logging
import time
import traceback
from typing import List, Optional, Union
from sqlalchemy.orm import Session
import pydantic

from app.ai import AIClient
from app.ai.exceptions import (
    AIConfigurationError,
    AIException,
    AIRateLimitError,
    AIResponseParsingError,
    AIServiceUnavailableError,
)
from app.mentor.analytics import AnalyticsEngine
from app.mentor.fifo import FIFOReconstructor
from app.mentor.models import MentorReview
from app.mentor.prioritizer import InsightPrioritizer
from app.mentor.rule_engine import RuleEngine
from app.mentor.schema import (
    AnalyticsMetrics,
    DailyMentorReview,
    HoldingItem,
    MentorContext,
    MentorResponse,
    MentorSummary,
    PublicMentorSummary,
    TradeInput,
    TradingGrade,
)
from app.stocks.service import get_cached_prices
from app.trades.enums import TradeType
from app.trades.models import Holding, Portfolio, Trade
from app.users.models import User

logger = logging.getLogger(__name__)


class MentorService:
    """
    Service layer orchestrating the end-to-end AI Mentor workflow.
    """

    SYSTEM_PROMPT = """You are an experienced trading mentor speaking directly to a trader.

You are NOT generating a trading analytics report.

The supplied context contains neutral quantitative facts calculated from the trader's actual activity.

Your task is to independently interpret those facts and explain what they mean in a direct, natural coaching conversation following this structure:
FACTS → INTERPRETATION → COACHING

CRITICAL BEHAVIORAL & EVIDENCE BOUNDARIES:
1. EVIDENCE BOUNDARY: Reason ONLY from the supplied neutral quantitative metrics. Distinguish clearly between:
   - FACT: What the metric directly establishes.
   - INTERPRETATION: What can reasonably be concluded from the metrics.
   - COACHING: What practical direction the trader should consider.
   Never present an interpretation as a known fact.

2. NO BEHAVIORAL HALLUCINATION: Do NOT claim or imply that the trader:
   - "lets winners run"
   - "cuts losses quickly"
   - "exits trades prematurely"
   - "has poor entries / trade selection"
   - "is emotional / panicking / chasing trades"
   - "is revenge trading or overtrading"
   - "lacks discipline or is careless"
   unless exact behavioral evidence is explicitly supplied in the context.

3. PRECISE METRIC INTERPRETATION:
   - profit_factor (e.g. 3.99): Aggregate gross profit is ~3.99x aggregate gross loss. Do NOT claim individual winning trades are larger or that the trader cuts losses quickly.
   - risk_reward_ratio (e.g. 2.0): Average profit relative to average loss is favorable. Do NOT infer how it was achieved.
   - win_rate_pct (e.g. 40): 40% of closed positions were profitable. Do NOT claim 40% is inherently good or bad, or that losses came from exiting prematurely.
   - max_position_sizing_pct (e.g. 65.39): The largest single position represented ~65.39% of capital allocation. Supports concentration-risk discussion.
   - portfolio_concentration_hhi (e.g. 4275.23): Exposure is highly concentrated. Do NOT invent specific holdings or trading behaviors.
   - max_drawdown_pct (e.g. 1.03): Peak-to-trough equity drop was 1.03%. Do NOT infer emotional or behavioral causes.
   - total_realized_pnl (e.g. 3260.02): Net profit for evaluated period. Do NOT claim long-term consistency beyond supplied data.

4. AVOID METRIC DUMPING & UNSUPPORTED CAUSALITY:
   - Select the 2-4 most important metrics and connect them into a coherent mentor observation.
   - Do NOT list all metrics or use phrases like "Your metrics show: X, Y, Z".
   - Do NOT invent arbitrary numerical limits (e.g., "limit positions to 10%", "use a 30-minute cooldown") unless explicitly supplied in context. Recommend directional adjustments instead.

5. COACHING STYLE & PRIORITIZATION:
   - Speak directly to the trader with calm confidence ("Here is what I see, here is why it matters, and here is what I'd focus on next.").
   - Prioritize the greatest practical risk (e.g. high position concentration matters more than increasing a 40% win rate when profit factor is 3.99).
   - Write a natural 3-5 sentence mentor analysis in mentor_message:
     1) Acknowledge the strongest positive signal.
     2) Identify the primary concern.
     3) Explain why the concern matters.
     4) Give one practical direction.

OUTPUT REQUIREMENT:
RESPOND ONLY WITH A VALID JSON OBJECT MATCHING THIS EXACT SCHEMA:
{
  "headline": "Short mentor-style headline",
  "mentor_message": "Natural 3-5 sentence mentor analysis directly addressing the trader.",
  "key_takeaway": "Single most important lesson in one concise sentence.",
  "risk_warning": "Important risk expressed naturally, or null if no major risk exists.",
  "next_focus": "One specific focus area for upcoming trades."
}"""

    def __init__(
        self,
        fifo_reconstructor: Optional[FIFOReconstructor] = None,
        analytics_engine: Optional[AnalyticsEngine] = None,
        rule_engine: Optional[RuleEngine] = None,
        prioritizer: Optional[InsightPrioritizer] = None,
        ai_client: Optional[AIClient] = None,
    ):
        self.fifo_reconstructor = fifo_reconstructor or FIFOReconstructor()
        self.analytics_engine = analytics_engine or AnalyticsEngine()
        self.rule_engine = rule_engine or RuleEngine()
        self.prioritizer = prioritizer or InsightPrioritizer()
        self.ai_client = ai_client or AIClient()

    async def generate_daily_review(
        self, db: Session, user_id: int, force_regenerate: bool = False
    ) -> DailyMentorReview:
        """
        Retrieves cached daily review or orchestrates fresh review generation and persists results.
        """
        logger.warning("mentor/daily-review Endpoint called")
        self._verify_user_exists(db, user_id)

        trade_count = db.query(Trade).filter(Trade.user_id == user_id).count()
        last_trade = (
            db.query(Trade)
            .filter(Trade.user_id == user_id)
            .order_by(Trade.created_at.desc(), Trade.id.desc())
            .first()
        )
        last_trade_id = str(last_trade.id) if last_trade else None

        cached_review = (
            db.query(MentorReview)
            .filter(MentorReview.user_id == user_id, MentorReview.review_type == "DAILY")
            .order_by(MentorReview.id.desc())
            .first()
        )

        is_ai_generated = (
            cached_review is not None
            and isinstance(cached_review.response_json, dict)
            and cached_review.response_json.get("_coaching_source") == "ai"
        )

        REQUIRED_COACHING_FIELDS = {"headline", "mentor_message", "key_takeaway", "next_focus"}

        is_new_schema = (
            cached_review is not None
            and isinstance(cached_review.response_json, dict)
            and REQUIRED_COACHING_FIELDS.issubset(cached_review.response_json.keys())
        )

        is_cache_valid = (
            not force_regenerate
            and cached_review is not None
            and not cached_review.stale # type: ignore
            and cached_review.trade_count == trade_count
            and cached_review.last_trade_id == last_trade_id
            and is_ai_generated
            and is_new_schema
        )

        if is_cache_valid and cached_review: # type: ignore
            try:
                full_summary = MentorSummary.model_validate(cached_review.summary_json)
                coaching_response = MentorResponse.model_validate(cached_review.response_json)
                public_summary = PublicMentorSummary(
                    trading_health_score=full_summary.trading_health_score,
                    portfolio_summary=full_summary.portfolio_summary,
                )
                logger.warning("AI_MENTOR_STAGE=cache_hit")
                return DailyMentorReview(
                    user_id=user_id,
                    review_date=cached_review.generated_at, # type: ignore
                    summary=public_summary,
                    coaching_response=coaching_response,
                )
            except Exception as e:
                logger.warning("Cached review schema invalidation (rebuilding AI review): %s", e)

        summary = self.generate_summary(db, user_id)
        coaching_response = await self._generate_coaching_response(summary)

        now_utc = datetime.now(timezone.utc)
        response_dict = coaching_response.model_dump()
        response_dict["_coaching_source"] = "ai"

        if cached_review:
            cached_review.health_score = summary.trading_health_score # type: ignore
            cached_review.trading_grade = summary.grade.value # type: ignore
            cached_review.summary_json = summary.model_dump() # type: ignore
            cached_review.response_json = response_dict # type: ignore
            cached_review.trade_count = trade_count # type: ignore
            cached_review.last_trade_id = last_trade_id # type: ignore
            cached_review.stale = False # type: ignore
            cached_review.generated_at = now_utc # type: ignore
            review_row = cached_review
        else:
            review_row = MentorReview(
                user_id=user_id,
                review_type="DAILY",
                health_score=summary.trading_health_score,
                trading_grade=summary.grade.value,
                summary_json=summary.model_dump(),
                response_json=response_dict,
                trade_count=trade_count,
                last_trade_id=last_trade_id,
                stale=False,
                generated_at=now_utc,
            )
            db.add(review_row)

        db.commit()
        db.refresh(review_row)
        logger.warning("AI_MENTOR_STAGE=response_persisted")

        public_summary = PublicMentorSummary(
            trading_health_score=summary.trading_health_score,
            portfolio_summary=summary.portfolio_summary,
        )

        daily_review = DailyMentorReview(
            user_id=user_id,
            review_date=review_row.generated_at, # type: ignore
            summary=public_summary,
            coaching_response=coaching_response,
        )
        logger.warning("AI_MENTOR_STAGE=api_response")
        return daily_review

    def mark_reviews_stale(self, db: Session, user_id: int) -> None:
        """Marks active mentor review cache entries stale for a user."""
        db.query(MentorReview).filter(
            MentorReview.user_id == user_id, MentorReview.stale == False
        ).update({"stale": True})
        db.commit()

    def generate_summary(self, db: Session, user_id: int) -> MentorSummary:
        """
        Orchestrates deterministic analytics, rule evaluation, and insight prioritization.
        """
        raw_trades = db.query(Trade).filter(Trade.user_id == user_id).order_by(Trade.created_at.asc()).all()
        normalized_trades = self._convert_orm_trades(raw_trades)

        holdings_items, portfolio_value = self._load_holdings_state(db, user_id)

        if not normalized_trades:
            return self._build_empty_trade_summary(holdings_items, portfolio_value)

        fifo_result = self.fifo_reconstructor.process_trades(normalized_trades)

        metrics = self.analytics_engine.calculate_metrics(
            closed_positions=fifo_result.closed_positions,
            total_raw_trades=len(normalized_trades),
            holdings=holdings_items,
            total_portfolio_value=portfolio_value,
            open_positions=list(fifo_result.open_positions.values()),
        )

        raw_insights = self.rule_engine.evaluate_all(
            metrics=metrics,
            closed_positions=fifo_result.closed_positions,
            holdings=holdings_items,
            raw_trades=normalized_trades,
        )

        return self.prioritizer.prioritize(metrics=metrics, insights=raw_insights)

    async def generate_trade_review(
        self, db: Session, user_id: int, trade_id: Union[int, str]
    ) -> MentorResponse:
        """
        Generates a focused mentor review for a specific trade execution.
        """
        target_trade = db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == user_id).first()
        if not target_trade:
            raise ValueError(f"Trade with ID {trade_id} not found for user {user_id}")

        summary = self.generate_summary(db, user_id)
        return await self._generate_coaching_response(summary)

    @staticmethod
    def _validate_llm_context(context_json: str) -> None:
        """Asserts that no RuleEngine identifiers, grades, or conclusions leak into the LLM context."""
        forbidden_tokens = [
            "MISTAKE_REVENGE_TRADING",
            "MISTAKE_FOMO_BUYING",
            "RISK_POSITION_SIZING",
            "MISTAKE_HOLDING_DURATION_ASYMMETRY",
            "RISK_REWARD_RATIO",
            "RISK_CONCENTRATION_HHI",
            "MISTAKE_OVERTRADING",
            "RISK_MAX_DRAWDOWN",
            "MISTAKE_STOP_LOSS_DISCIPLINE",
            "RISK_POSITION_AND_DIVERSIFICATION",
            "rule_id",
            "triggered_evidence",
            "coaching_message",
            "action_item",
            "losing_symbol",
            "next_symbol",
            "Revenge Trading Detected",
            "Overtrading Frequency Alert",
            "Position Sizing & Concentration Risk",
            "Excellent Risk-Reward Ratio",
            "Sub-optimal Risk-Reward Ratio",
            "Holding Losing Positions Too Long",
            "Unmanaged Large Losses Detected",
            "FOMO Momentum Chasing",
            "Oversized Position Allocation",
            "Severe Capital Drawdown",
            "High Portfolio Concentration",
            "primary_focus",
            "improvement_focus",
            "all_insights",
            "top_mistakes",
            "top_risks",
            "top_strengths",
            "HIGH_RISK",
            "MASTER",
            "DISCIPLINED",
            "AVERAGE",
            "NEEDS_WORK",
            "grade",
            "AXISBANK",
            "HDFCBANK",
        ]

        for token in forbidden_tokens:
            assert token not in context_json, (
                f"Forbidden identifier or conclusion leaked into LLM context: {token}"
            )

    async def _generate_coaching_response(self, summary: MentorSummary) -> MentorResponse:
        """Generates AI coaching response via OpenRouter. Raises AIException on failure without fallback."""
        context = self._build_mentor_context(summary)
        logger.warning("AI_MENTOR_STAGE=context_built")

        context_json_str = context.model_dump_json(indent=2)
        self._validate_llm_context(context_json_str)

        user_prompt = f"Analyze these trading facts and return the structured JSON coaching response:\n\n{context_json_str}"

        model_name = getattr(self.ai_client.provider, "model_name", "deepseek/deepseek-chat-v3")

        logger.warning("AI_MENTOR_STAGE=llm_request")
        logger.warning("AI_MENTOR_LLM_REQUEST_BEGIN")
        logger.warning("AI_MENTOR_LLM_CONTEXT=%s", user_prompt)
        logger.warning("AI_MENTOR_LLM_REQUEST_END")

        try:
            raw_json_str = await self.ai_client.generate_async(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_mime_type="application/json",
            )
            logger.warning("AI_MENTOR_STAGE=llm_raw_response")
            logger.warning("AI_MENTOR_RAW_LLM_RESPONSE_BEGIN")
            logger.warning(
                "AI_MENTOR_RAW_LLM_RESPONSE | provider=OpenRouter | model=%s | raw=%s",
                model_name,
                raw_json_str,
            )
            logger.warning("AI_MENTOR_RAW_LLM_RESPONSE_END")

            response = MentorResponse.model_validate_json(raw_json_str)
            logger.warning("AI_MENTOR_STAGE=response_validated")
            return response
        except (json.JSONDecodeError, Exception) as e:
            if isinstance(e, (json.JSONDecodeError, ValueError, pydantic.ValidationError)):
                logger.error("Mentor AI response validation failed (%s): %s", type(e).__name__, e)
                raise AIResponseParsingError(f"Invalid AI JSON response format: {e}") from e
            if isinstance(e, (AIConfigurationError, AIServiceUnavailableError, AIRateLimitError, AIResponseParsingError)):
                logger.error("Mentor AI generation failed (%s): %s", type(e).__name__, e)
                raise
            logger.error("Unexpected error during Mentor AI generation (%s): %s", type(e).__name__, e)
            raise AIServiceUnavailableError(f"Unexpected AI provider failure: {e}") from e

    @staticmethod
    def _build_mentor_context(summary: MentorSummary) -> MentorContext:
        """Constructs compact MentorContext containing neutral deterministic metrics without grade."""
        return MentorContext(
            health_score=summary.trading_health_score,
            win_rate_pct=float(summary.portfolio_summary.get("win_rate_pct", 0.0)),
            total_realized_pnl=float(summary.portfolio_summary.get("total_realized_pnl", 0.0)),
            profit_factor=float(summary.portfolio_summary.get("profit_factor", 0.0)),
            risk_reward_ratio=float(summary.portfolio_summary.get("risk_reward_ratio", 0.0)),
            max_drawdown_pct=float(summary.portfolio_summary.get("max_drawdown_pct", 0.0)),
            holding_duration_ratio=float(summary.portfolio_summary.get("holding_duration_ratio", 0.0)),
            max_position_sizing_pct=float(summary.portfolio_summary.get("max_position_sizing_pct", 0.0)),
            total_trades_count=int(summary.portfolio_summary.get("total_trades_count", 0)),
            closed_positions_count=int(summary.portfolio_summary.get("closed_positions_count", 0)),
            portfolio_concentration_hhi=float(summary.portfolio_summary.get("portfolio_concentration_hhi", 0.0)),
        )

    @staticmethod
    def _verify_user_exists(db: Session, user_id: int) -> None:
        """Validates user existence in database."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User with ID {user_id} does not exist")

    @staticmethod
    def _convert_orm_trades(raw_trades: List[Trade]) -> List[TradeInput]:
        """Converts raw SQLAlchemy Trade ORM rows into normalized TradeInput dataclasses."""
        inputs = []
        for t in raw_trades:
            trade_type_str = t.trade_type.value if isinstance(t.trade_type, TradeType) else str(t.trade_type)
            inputs.append(
                TradeInput(
                    id=t.id,
                    symbol=t.symbol,
                    quantity=t.quantity,
                    price=float(t.price),
                    trade_type=trade_type_str,
                    created_at=t.created_at,
                )
            )
        return inputs

    @staticmethod
    def _load_holdings_state(db: Session, user_id: int) -> tuple[List[HoldingItem], float]:
        """Loads user holdings and total portfolio market value using get_cached_prices."""
        portfolio = db.query(Portfolio).filter(Portfolio.user_id == user_id).first()
        holdings = db.query(Holding).filter(Holding.user_id == user_id, Holding.quantity > 0).all()

        cash_balance = (
            (portfolio.available_balance + portfolio.reserved_balance)
            if portfolio
            else 100000.0
        )

        if not holdings:
            return [], cash_balance

        symbols = [h.symbol for h in holdings]
        prices_map = get_cached_prices(symbols)

        holding_items = []
        for h in holdings:
            avg_price = float(h.avg_price or 0.0)
            price_tuple = prices_map.get(h.symbol)
            live_price = price_tuple[0] if price_tuple and price_tuple[0] > 0 else None
            current_price = live_price if live_price is not None else avg_price
            current_value = float(h.quantity * current_price)
            holding_items.append(
                HoldingItem(
                    symbol=h.symbol,
                    quantity=h.quantity,
                    avg_price=avg_price,
                    current_price=current_price,
                    current_value=current_value,
                )
            )

        total_portfolio_value = cash_balance + sum(item.current_value for item in holding_items)
        return holding_items, total_portfolio_value

    @staticmethod
    def _build_empty_trade_summary(holdings: List[HoldingItem], portfolio_value: float) -> MentorSummary:
        """Constructs a clean default summary when no trades have been executed yet."""
        metrics = AnalyticsMetrics(
            total_trades_count=0,
            closed_positions_count=0,
            winning_positions_count=0,
            losing_positions_count=0,
            breakeven_positions_count=0,
            win_rate_pct=0.0,
            total_realized_pnl=0.0,
            total_gross_profit=0.0,
            total_gross_loss=0.0,
            average_profit=0.0,
            average_loss=0.0,
            profit_factor=0.0,
            risk_reward_ratio=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_amount=0.0,
            avg_holding_duration_minutes=0.0,
            avg_winning_duration_minutes=0.0,
            avg_losing_duration_minutes=0.0,
            holding_duration_ratio=0.0,
            portfolio_concentration_hhi=0.0,
            max_position_sizing_pct=0.0,
            avg_position_sizing_pct=0.0,
            total_unrealized_pnl=0.0,
        )
        return MentorSummary(
            trading_health_score=100.0,
            grade=TradingGrade.MASTER,
            portfolio_summary={
                "trading_health_score": 100.0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "risk_reward_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "holding_duration_ratio": 0.0,
                "max_position_sizing_pct": 0.0,
                "portfolio_concentration_hhi": 0.0,
                "total_realized_pnl": 0.0,
                "total_trades_count": 0,
                "closed_positions_count": 0,
                "sub_scores": {
                    "risk_management": 100.0,
                    "execution_discipline": 100.0,
                    "profitability": 100.0,
                    "capital_preservation": 100.0,
                    "diversification": 100.0,
                },
            },
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=[],
            improvement_focus="Execution Discipline",
            all_insights=[],
        )


mentor_service = MentorService()
