"""
Mentor Service Orchestration Layer.

Orchestrates trade loading, FIFO position reconstruction, analytics calculations,
rule evaluations, insight prioritization, response generation, and review persistence.
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional, Union
from sqlalchemy.orm import Session

from app.mentor.analytics import AnalyticsEngine
from app.mentor.fifo import FIFOReconstructor
from app.mentor.mentor_generator import MentorGenerator
from app.mentor.models import MentorReview
from app.mentor.prioritizer import InsightPrioritizer
from app.mentor.rule_engine import RuleEngine
from app.mentor.schema import (
    AnalyticsMetrics,
    DailyMentorReview,
    HoldingItem,
    MentorResponse,
    MentorSummary,
    TradeInput,
    TradingGrade,
)
from app.mentor.template_generator import TemplateGenerator
from app.stocks.service import get_cached_prices
from app.trades.enums import TradeType
from app.trades.models import Holding, Portfolio, Trade
from app.users.models import User

logger = logging.getLogger(__name__)


class MentorService:
    """
    Service layer orchestrating the end-to-end AI Mentor workflow.
    """

    def __init__(
        self,
        fifo_reconstructor: Optional[FIFOReconstructor] = None,
        analytics_engine: Optional[AnalyticsEngine] = None,
        rule_engine: Optional[RuleEngine] = None,
        prioritizer: Optional[InsightPrioritizer] = None,
        mentor_generator: Optional[MentorGenerator] = None,
    ):
        self.fifo_reconstructor = fifo_reconstructor or FIFOReconstructor()
        self.analytics_engine = analytics_engine or AnalyticsEngine()
        self.rule_engine = rule_engine or RuleEngine()
        self.prioritizer = prioritizer or InsightPrioritizer()
        self.mentor_generator = mentor_generator or MentorGenerator()

    def generate_daily_review(
        self, db: Session, user_id: int, force_regenerate: bool = False
    ) -> DailyMentorReview:
        """
        Retrieves cached daily review or orchestrates fresh review generation and persists results.
        """
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

        is_cache_valid = (
            not force_regenerate
            and cached_review is not None
            and not cached_review.stale
            and cached_review.trade_count == trade_count
            and cached_review.last_trade_id == last_trade_id
        )

        if is_cache_valid and cached_review:
            summary = MentorSummary.model_validate(cached_review.summary_json)
            coaching_response = MentorResponse.model_validate(cached_review.response_json)
            return DailyMentorReview(
                user_id=user_id,
                review_date=cached_review.generated_at,
                summary=summary,
                coaching_response=coaching_response,
            )

        summary = self.generate_summary(db, user_id)

        try:
            coaching_response = self.mentor_generator.generate(summary)
        except Exception as e:
            logger.warning("MentorGenerator failed (%s). Falling back to TemplateGenerator.", e)
            coaching_response = TemplateGenerator.generate_response(summary)

        now_utc = datetime.now(timezone.utc)

        if cached_review:
            cached_review.health_score = summary.trading_health_score
            cached_review.trading_grade = summary.grade.value
            cached_review.summary_json = summary.model_dump()
            cached_review.response_json = coaching_response.model_dump()
            cached_review.trade_count = trade_count
            cached_review.last_trade_id = last_trade_id
            cached_review.stale = False
            cached_review.generated_at = now_utc
            review_row = cached_review
        else:
            review_row = MentorReview(
                user_id=user_id,
                review_type="DAILY",
                health_score=summary.trading_health_score,
                trading_grade=summary.grade.value,
                summary_json=summary.model_dump(),
                response_json=coaching_response.model_dump(),
                trade_count=trade_count,
                last_trade_id=last_trade_id,
                stale=False,
                generated_at=now_utc,
            )
            db.add(review_row)

        db.commit()
        db.refresh(review_row)

        return DailyMentorReview(
            user_id=user_id,
            review_date=review_row.generated_at,
            summary=summary,
            coaching_response=coaching_response,
        )

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
        self._verify_user_exists(db, user_id)

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

    def generate_trade_review(
        self, db: Session, user_id: int, trade_id: Union[int, str]
    ) -> MentorResponse:
        """
        Generates a focused mentor review for a specific trade execution.
        """
        target_trade = db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == user_id).first()
        if not target_trade:
            raise ValueError(f"Trade with ID {trade_id} not found for user {user_id}")

        summary = self.generate_summary(db, user_id)
        return self.mentor_generator.generate(summary)

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

        portfolio_summary = {
            "trading_health_score": 100.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
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
        }

        return MentorSummary(
            trading_health_score=100.0,
            grade=TradingGrade.MASTER,
            portfolio_summary=portfolio_summary,
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=["Place your first paper trade to begin receiving AI Mentor feedback."],
            improvement_focus="Discipline",
            all_insights=[],
        )


mentor_service = MentorService()
