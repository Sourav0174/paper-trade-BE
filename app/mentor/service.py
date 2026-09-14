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
    Severity,
    SingleTradeContext,
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

    TRADE_SYSTEM_PROMPT = """You are an elite trading psychologist and quantitative execution coach for Paper Trade.
Your task is to analyze a single executed trade and provide structured, insightful coaching on this specific trade.

CRITICAL EXECUTION GUIDELINES:
1. FOCUS ON THIS SPECIFIC TRADE: The subject of your analysis is the provided trade (symbol, price, quantity, trade type, outcome).
2. ACCURATE FINANCIAL FACTS: Strictly reference the provided numbers (execution price, realized/unrealized P&L, holding duration, position allocation). Never invent prices or P&L.
3. EXECUTION EVALUATION:
   - Evaluate whether position sizing was disciplined (allocation > 20% is elevated, > 50% is high risk).
   - If this trade was entered shortly after a loss (is_after_recent_loss is true), address emotional impulse risk constructively.
   - If the trade was profitable, reinforce what went right (risk/reward, patience) and warn against overconfidence.
   - If the trade was a loss, coach on loss acceptance, stop-loss discipline, and preventing revenge trades.
   - If the trade is still open, coach on active trade management and planning the exit.
4. TONE: Direct, encouraging, professional, and grounded in disciplined trading psychology.

RESPOND ONLY WITH A VALID JSON OBJECT MATCHING THIS EXACT SCHEMA:
{
  "headline": "Short natural headline about this specific trade (max 8 words)",
  "mentor_message": "2-3 paragraphs analyzing this specific trade execution, risk factors, and psychological discipline",
  "key_takeaway": "Single most important lesson from this trade execution (1 sentence)",
  "risk_warning": "Specific risk warning for this trade or null if risk was well-managed",
  "next_focus": "Primary focus area (e.g., 'Position Sizing', 'Loss Acceptance', 'Execution Discipline', 'Profit Protection')"
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
        coaching_source = "ai"
        try:
            coaching_response = await self._generate_coaching_response(summary)
        except Exception as e:
            logger.warning(
                "AI generation failed (%s: %s). Activating deterministic coaching fallback.",
                type(e).__name__,
                e,
            )
            logger.warning("AI_MENTOR_STAGE=deterministic_fallback")
            coaching_response = self._synthesize_fallback_coaching(summary)
            coaching_source = "deterministic_fallback"

        now_utc = datetime.now(timezone.utc)
        response_dict = coaching_response.model_dump()
        response_dict["_coaching_source"] = coaching_source

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
        Generates a focused, trade-specific mentor review for an individual trade execution.
        """
        self._verify_user_exists(db, user_id)

        trade_id_int = int(trade_id) if str(trade_id).isdigit() else -1
        target_trade = db.query(Trade).filter(Trade.id == trade_id_int, Trade.user_id == user_id).first()
        if not target_trade:
            raise ValueError(f"Trade with ID {trade_id} not found for user {user_id}")

        context = self._build_single_trade_context(db, user_id, target_trade)

        try:
            return await self._generate_trade_coaching_response(context)
        except Exception as e:
            logger.warning(
                "Trade AI generation failed (%s: %s). Activating deterministic trade fallback.",
                type(e).__name__,
                e,
            )
            return self._synthesize_single_trade_fallback(context)

    def _build_single_trade_context(
        self, db: Session, user_id: int, target_trade: Trade
    ) -> SingleTradeContext:
        """Constructs deterministic, factual single-trade context from ORM trade and FIFO reconstruction."""
        raw_trades = db.query(Trade).filter(Trade.user_id == user_id).order_by(Trade.created_at.asc()).all()
        normalized_trades = self._convert_orm_trades(raw_trades)

        holdings_items, portfolio_value = self._load_holdings_state(db, user_id)
        fifo_result = self.fifo_reconstructor.process_trades(normalized_trades)

        trade_type = (
            target_trade.trade_type.value
            if hasattr(target_trade.trade_type, "value")
            else str(target_trade.trade_type).upper()
        )
        trade_price = float(target_trade.price)
        trade_qty = int(target_trade.quantity)
        trade_value = round(trade_qty * trade_price, 2)
        allocation_pct = round((trade_value / portfolio_value) * 100, 2) if portfolio_value > 0 else 0.0

        # Check for recent loss prior to this trade (Revenge trading signal: loss closed <= 15 mins before entry)
        is_after_recent_loss = False
        target_time = target_trade.created_at
        for c in fifo_result.closed_chunks:
            if (
                c.pnl < 0
                and str(c.sell_trade_id) != str(target_trade.id)
                and str(c.buy_trade_id) != str(target_trade.id)
                and c.sell_timestamp <= target_time
            ):
                time_diff_min = (target_time - c.sell_timestamp).total_seconds() / 60.0
                if 0.0 <= time_diff_min <= 15.0:
                    is_after_recent_loss = True
                    break

        # Check matched chunks for this trade
        realized_pnl: Optional[float] = None
        realized_pnl_pct: Optional[float] = None
        avg_entry: Optional[float] = None
        avg_exit: Optional[float] = None
        duration_min: Optional[float] = None
        is_closed = False

        if trade_type == "SELL":
            matching_chunks = [c for c in fifo_result.closed_chunks if str(c.sell_trade_id) == str(target_trade.id)]
            if matching_chunks:
                is_closed = True
                matched_qty = sum(c.quantity for c in matching_chunks)
                total_pnl = sum(c.pnl for c in matching_chunks)
                total_cost = sum(c.buy_price * c.quantity for c in matching_chunks)
                realized_pnl = round(total_pnl, 2)
                realized_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost > 0 else 0.0
                avg_entry = round(total_cost / matched_qty, 2) if matched_qty > 0 else trade_price
                avg_exit = trade_price
                duration_min = round(
                    sum(c.duration_minutes * c.quantity for c in matching_chunks) / matched_qty, 1
                ) if matched_qty > 0 else 0.0
        else:  # BUY
            matching_chunks = [c for c in fifo_result.closed_chunks if str(c.buy_trade_id) == str(target_trade.id)]
            if matching_chunks:
                is_closed = True
                closed_qty = sum(c.quantity for c in matching_chunks)
                total_pnl = sum(c.pnl for c in matching_chunks)
                total_proceeds = sum(c.sell_price * c.quantity for c in matching_chunks)
                total_cost = trade_price * closed_qty
                realized_pnl = round(total_pnl, 2)
                realized_pnl_pct = round((total_pnl / total_cost) * 100, 2) if total_cost > 0 else 0.0
                avg_entry = trade_price
                avg_exit = round(total_proceeds / closed_qty, 2) if closed_qty > 0 else None
                duration_min = round(
                    sum(c.duration_minutes * c.quantity for c in matching_chunks) / closed_qty, 1
                ) if closed_qty > 0 else 0.0
            else:
                avg_entry = trade_price

        # Portfolio overall metrics for grounding
        total_closed = len(fifo_result.closed_positions)
        win_positions = sum(1 for p in fifo_result.closed_positions if p.is_win)
        win_rate = round((win_positions / total_closed) * 100, 1) if total_closed > 0 else 0.0

        return SingleTradeContext(
            symbol=target_trade.symbol,
            trade_type=trade_type,
            quantity=trade_qty,
            execution_price=trade_price,
            trade_value=trade_value,
            position_allocation_pct=allocation_pct,
            is_closed=is_closed,
            realized_pnl=realized_pnl,
            realized_pnl_pct=realized_pnl_pct,
            avg_entry_price=avg_entry,
            avg_exit_price=avg_exit,
            holding_duration_minutes=duration_min,
            is_after_recent_loss=is_after_recent_loss,
            portfolio_total_trades=len(normalized_trades),
            portfolio_win_rate_pct=win_rate,
        )

    async def _generate_trade_coaching_response(
        self, context: SingleTradeContext
    ) -> MentorResponse:
        """Invokes LLM with validated trade-specific context and TRADE_SYSTEM_PROMPT."""
        context_json = json.dumps(context.model_dump(), indent=2, default=str)
        self._validate_llm_context(context_json)

        user_prompt = (
            f"Analyze this executed trade and return the structured JSON coaching response:\n\n"
            f"{context_json}"
        )

        model_name = getattr(getattr(self.ai_client, "provider", None), "model_name", "unknown")
        logger.warning("AI_TRADE_REVIEW_LLM_REQUEST_BEGIN")
        logger.warning("AI_TRADE_REVIEW_LLM_CONTEXT=%s", user_prompt)
        logger.warning("AI_TRADE_REVIEW_LLM_REQUEST_END")

        raw_json_str = await self.ai_client.generate_async(
            system_prompt=self.TRADE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_mime_type="application/json",
        )
        logger.warning(
            "AI_TRADE_REVIEW_RAW_LLM_RESPONSE | model=%s | raw=%s",
            model_name,
            raw_json_str,
        )

        return MentorResponse.model_validate_json(raw_json_str)

    @staticmethod
    def _synthesize_single_trade_fallback(context: SingleTradeContext) -> MentorResponse:
        """Produces high-value, deterministic coaching for a single executed trade when LLM fails or times out."""
        symbol = context.symbol
        trade_type = context.trade_type
        price = context.execution_price
        qty = context.quantity
        val = context.trade_value
        alloc = context.position_allocation_pct
        pnl = context.realized_pnl
        pnl_pct = context.realized_pnl_pct
        is_closed = context.is_closed
        is_revenge = context.is_after_recent_loss
        win_rate = context.portfolio_win_rate_pct

        # 1. Headline
        if trade_type == "SELL" and pnl is not None:
            if pnl > 0:
                headline = f"Disciplined Win on {symbol} (+${pnl:,.2f})"
            elif pnl < 0:
                headline = f"Controlled Loss on {symbol} (-${abs(pnl):,.2f})"
            else:
                headline = f"Breakeven Exit on {symbol}"
        elif is_revenge:
            headline = f"Caution on {symbol} — Rapid Re-Entry"
        elif alloc > 50.0:
            headline = f"High Position Sizing on {symbol} ({alloc:.1f}%)"
        else:
            headline = f"{trade_type.capitalize()} Execution on {symbol} @ ${price:,.2f}"

        # 2. Mentor Message
        paragraphs: List[str] = []

        # Para 1: Execution & Outcome facts
        p1 = (
            f"You executed a {trade_type} of {qty} shares of {symbol} at ${price:,.2f} "
            f"for a total capital commitment of ${val:,.2f} ({alloc:.1f}% of portfolio)."
        )
        if is_closed and pnl is not None:
            pnl_sign = "+" if pnl >= 0 else "-"
            entry_txt = f" from average entry of ${context.avg_entry_price:,.2f}" if context.avg_entry_price else ""
            dur_txt = (
                f" over a holding duration of {context.holding_duration_minutes:.1f} minutes"
                if context.holding_duration_minutes
                else ""
            )
            p1 += f" This trade realized {pnl_sign}${abs(pnl):,.2f} ({pnl_pct:+.1f}%){entry_txt}{dur_txt}."
        elif not is_closed and trade_type == "BUY":
            p1 += " This position is currently active in your portfolio."
        paragraphs.append(p1)

        # Para 2: Behavioral & Risk Diagnostic
        if is_revenge:
            paragraphs.append(
                "This execution occurred within 15 minutes of closing a losing position. "
                "Rapid re-entry following a loss is a common marker for emotional revenge trading. "
                "Ensure your trade setup was validated by your technical rules rather than an impulse to recover lost capital."
            )
        elif alloc > 50.0:
            paragraphs.append(
                f"Allocating {alloc:.1f}% of total portfolio capital to a single position introduces severe concentration risk. "
                "Even high-probability setups can experience adverse market moves, and outsized positions magnify portfolio drawdowns."
            )
        elif is_closed and pnl is not None and pnl > 0:
            paragraphs.append(
                "This execution captured a solid gain with disciplined risk management. "
                "Taking profits according to your trading plan is critical for maintaining consistency. "
                "Avoid rolling profits immediately into higher-risk trades."
            )
        elif is_closed and pnl is not None and pnl < 0:
            paragraphs.append(
                "Taking a loss is a natural and unavoidable component of trading. "
                "The key to long-term success is keeping losses small and adhering strictly to stop-loss levels. "
                "Accept the result cleanly and wait patiently for your next valid setup."
            )
        else:
            paragraphs.append(
                "The execution sizing was managed within measured risk bounds. "
                "Continue executing with patience, maintaining predefined stops and targets on every position."
            )

        # Para 3: Actionable guidance
        if is_revenge:
            paragraphs.append("Recommended action: Take a mandatory 15-30 minute pause away from the charts following any closed loss.")
        elif alloc > 50.0:
            paragraphs.append("Recommended action: Cap individual position sizing to at most 10-20% of your total trading capital.")
        else:
            paragraphs.append(f"Across your portfolio, your overall win rate is {win_rate:.1f}%. Keep prioritizing process over individual trade outcomes.")

        mentor_message = "\n\n".join(paragraphs)

        # 3. Key Takeaway
        if is_revenge:
            key_takeaway = "Step away after a loss to ensure next entries follow your system, not emotions."
        elif alloc > 50.0:
            key_takeaway = "Cap position size to prevent a single trade from creating an outsized portfolio drawdown."
        elif is_closed and pnl is not None and pnl > 0:
            key_takeaway = "Lock in profits according to your plan and avoid overconfidence after winning trades."
        elif is_closed and pnl is not None and pnl < 0:
            key_takeaway = "Accept small losses cleanly; they protect your capital for the next opportunity."
        else:
            key_takeaway = "Execute strictly within your predefined trading rules and position sizing boundaries."

        # 4. Risk Warning
        risk_warning: Optional[str] = None
        if is_revenge:
            risk_warning = "Possible Revenge Trading: Executed within 15 minutes of closing a loss."
        elif alloc > 50.0:
            risk_warning = f"High Sizing Exposure: Single position represents {alloc:.1f}% of total portfolio."

        # 5. Next Focus
        if is_revenge:
            next_focus = "Emotional Discipline"
        elif is_closed and pnl is not None and pnl < 0:
            next_focus = "Loss Acceptance"
        elif alloc > 50.0:
            next_focus = "Position Sizing"
        elif is_closed and pnl is not None and pnl > 0:
            next_focus = "Profit Protection"
        else:
            next_focus = "Execution Discipline"

        return MentorResponse(
            headline=headline,
            mentor_message=mentor_message,
            key_takeaway=key_takeaway,
            risk_warning=risk_warning,
            next_focus=next_focus,
        )

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
    def _synthesize_fallback_coaching(summary: MentorSummary) -> MentorResponse:
        """
        Synthesizes high-value deterministic coaching from RuleEngine insights and portfolio analytics
        when external LLM providers fail, time out, or are rate limited.
        """
        health_score = summary.trading_health_score
        portfolio = summary.portfolio_summary
        total_trades = int(portfolio.get("total_trades_count", 0))
        win_rate = float(portfolio.get("win_rate_pct", 0.0))
        realized_pnl = float(portfolio.get("total_realized_pnl", 0.0))

        top_strengths = summary.top_strengths
        top_mistakes = summary.top_mistakes
        top_risks = summary.top_risks
        action_items = summary.action_items
        focus = summary.improvement_focus or "Execution Discipline"

        # 1. Headline
        if total_trades == 0:
            headline = "Clean Slate — Ready for Your First Trade"
        elif top_mistakes:
            headline = f"Focus on {focus} — {top_mistakes[0].title}"
        elif top_risks:
            headline = f"Risk Alert — Manage {top_risks[0].title}"
        elif health_score >= 80.0:
            headline = "Strong Trading Discipline — Protect Your Edge"
        elif health_score >= 60.0:
            headline = "Solid Foundation — Refining Risk & Consistency"
        else:
            headline = f"Priority Focus: {focus} & Capital Preservation"

        # 2. Mentor Message (structured multi-paragraph guidance)
        paragraphs: List[str] = []

        if total_trades == 0:
            paragraphs.append(
                "You have a clean slate with zero closed trades. Before entering the market, "
                "establish a structured trading plan with predefined position limits and exit rules."
            )
            paragraphs.append(
                "When your first setup triggers, focus purely on execution discipline rather than "
                "the financial outcome of the individual trade."
            )
        else:
            # Performance Context Paragraph
            pnl_str = f"+${realized_pnl:,.2f}" if realized_pnl >= 0 else f"-${abs(realized_pnl):,.2f}"
            perf_intro = (
                f"Your trading health score stands at {health_score:.1f}/100 with a win rate of "
                f"{win_rate:.1f}% and net realized P&L of {pnl_str} across {total_trades} trade(s)."
            )
            if top_strengths:
                s = top_strengths[0]
                perf_intro += f" A key strength in your data is {s.title.lower()} ({s.description})."
            paragraphs.append(perf_intro)

            # Core Diagnostic Paragraph
            if top_mistakes:
                m = top_mistakes[0]
                mistake_msg = f"The primary area requiring attention is {m.title.lower()}: {m.description}"
                if len(top_mistakes) > 1:
                    m2 = top_mistakes[1]
                    mistake_msg += f" Watch out also for {m2.title.lower()} ({m2.description})."
                paragraphs.append(mistake_msg)
            elif top_risks:
                r = top_risks[0]
                paragraphs.append(
                    f"While no severe behavioral mistakes were flagged, portfolio risk requires monitoring: "
                    f"{r.title} ({r.description})."
                )
            else:
                paragraphs.append(
                    "Your execution remains well within healthy risk parameters. Continue maintaining "
                    "consistent sizing and adhering strictly to your entry and exit criteria."
                )

            # Action / Forward Guidance Paragraph
            if action_items:
                action_text = " ".join(f"{i+1}. {item}" for i, item in enumerate(action_items[:2]))
                paragraphs.append(f"Immediate recommendations to improve your consistency: {action_text}")
            else:
                paragraphs.append(
                    f"Keep your primary focus on {focus.lower()} and protect your capital against outsized drawdowns."
                )

        mentor_message = "\n\n".join(paragraphs)

        # 3. Key Takeaway
        if action_items:
            key_takeaway = action_items[0]
        elif top_mistakes and top_mistakes[0].action_item:
            key_takeaway = top_mistakes[0].action_item
        elif top_mistakes:
            key_takeaway = top_mistakes[0].description
        elif top_risks and top_risks[0].action_item:
            key_takeaway = top_risks[0].action_item
        elif total_trades == 0:
            key_takeaway = "Take your first trade only when a valid strategy setup appears."
        else:
            key_takeaway = "Maintain strict risk discipline and adhere to your position sizing limits."

        # 4. Risk Warning
        risk_warning: Optional[str] = None
        if top_risks:
            r = top_risks[0]
            risk_warning = f"{r.title}: {r.description}"
        elif top_mistakes:
            critical_mistakes = [m for m in top_mistakes if m.severity in (Severity.CRITICAL, Severity.HIGH)]
            if critical_mistakes:
                cm = critical_mistakes[0]
                risk_warning = f"{cm.title}: {cm.description}"

        # 5. Next Focus
        next_focus = focus

        return MentorResponse(
            headline=headline,
            mentor_message=mentor_message,
            key_takeaway=key_takeaway,
            risk_warning=risk_warning,
            next_focus=next_focus,
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
