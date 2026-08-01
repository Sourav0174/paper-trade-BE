"""
Unit tests for AI Mentor Phase 4 Review Persistence and Orchestration (app/mentor/service.py).

Tests:
- End-to-end orchestration flow (generate_daily_review, generate_summary, generate_trade_review)
- Review persistence and DB caching (cache hit, cache miss, force regenerate)
- Stale review invalidation
- Handling edge cases (no trades, invalid user, AI failure fallback)
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock

from app.mentor.models import MentorReview
from app.mentor.schema import (
    AnalyticsMetrics,
    DailyMentorReview,
    MentorResponse,
    MentorSummary,
    TradingGrade,
)
from app.mentor.service import MentorService
from app.trades.models import Trade
from app.users.models import User


class TestMentorService(unittest.TestCase):

    def setUp(self):
        """Set up mock DB session and dependencies for MentorService tests."""
        self.db = MagicMock()

        # Mock User ORM query
        self.mock_user = MagicMock()
        self.mock_user.id = 1

        # Mock Portfolio & Holdings ORM queries
        self.mock_portfolio = MagicMock()
        self.mock_portfolio.available_balance = 100000.0
        self.mock_portfolio.reserved_balance = 0.0
        self.mock_portfolio.invested_amount = 0.0

    def test_invalid_user_raises_value_error(self):
        """Test MentorService raises ValueError when user_id is not found."""
        self.db.query().filter().first.return_value = None

        service = MentorService()
        with self.assertRaises(ValueError):
            service.generate_daily_review(self.db, user_id=999)

    def test_no_trades_returns_clean_default_review(self):
        """Test MentorService handles user with 0 trades gracefully."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        service = MentorService()
        review = service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertEqual(review.user_id, 1)
        self.assertEqual(review.summary.trading_health_score, 100.0)
        self.assertEqual(review.summary.portfolio_summary["total_trades_count"], 0)
        self.assertIn("Place your first paper trade", review.summary.action_items[0])

    def test_orchestration_flow_with_dependency_injection(self):
        """Test full orchestration workflow using injected mock components."""
        mock_fifo = MagicMock()
        mock_fifo_result = MagicMock()
        mock_fifo_result.closed_positions = []
        mock_fifo_result.open_positions = {}
        mock_fifo.process_trades.return_value = mock_fifo_result

        mock_analytics = MagicMock()
        mock_metrics = AnalyticsMetrics(
            total_trades_count=2,
            closed_positions_count=1,
            winning_positions_count=1,
            losing_positions_count=0,
            breakeven_positions_count=0,
            win_rate_pct=100.0,
            total_realized_pnl=500.0,
            total_gross_profit=500.0,
            total_gross_loss=0.0,
            average_profit=500.0,
            average_loss=0.0,
            profit_factor=3.0,
            risk_reward_ratio=2.0,
            max_drawdown_pct=0.0,
            max_drawdown_amount=0.0,
            avg_holding_duration_minutes=20.0,
            avg_winning_duration_minutes=20.0,
            avg_losing_duration_minutes=0.0,
            holding_duration_ratio=0.0,
            portfolio_concentration_hhi=500.0,
            max_position_sizing_pct=10.0,
            avg_position_sizing_pct=10.0,
            total_unrealized_pnl=0.0,
        )
        mock_analytics.calculate_metrics.return_value = mock_metrics

        mock_rule_engine = MagicMock()
        mock_rule_engine.evaluate_all.return_value = []

        mock_prioritizer = MagicMock()
        mock_summary = MentorSummary(
            trading_health_score=90.0,
            grade=TradingGrade.MASTER,
            portfolio_summary={},
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=["Maintain discipline."],
            improvement_focus="Discipline",
            all_insights=[],
        )
        mock_prioritizer.prioritize.return_value = mock_summary

        mock_generator = MagicMock()
        mock_response = MentorResponse(
            headline="Great Job",
            summary="Disciplined execution.",
            strengths=["Discipline"],
            mistakes=[],
            risk_warning=None,
            action_items=["Maintain discipline."],
            motivation="Keep it up.",
            next_focus="Discipline",
        )
        mock_generator.generate.return_value = mock_response

        mock_trade1 = MagicMock()
        mock_trade1.id = 101
        mock_trade1.symbol = "RELIANCE"
        mock_trade1.quantity = 10
        mock_trade1.price = 2500.0
        mock_trade1.trade_type.value = "BUY"
        mock_trade1.created_at = datetime.now(timezone.utc)

        def query_side_effect(model):
            mock_q = MagicMock()
            if model == User:
                mock_q.filter().first.return_value = self.mock_user
            elif model == Trade:
                mock_q.filter().count.return_value = 1
                mock_q.filter().order_by().first.return_value = mock_trade1
                mock_q.filter().order_by().all.return_value = [mock_trade1]
            elif model == MentorReview:
                mock_q.filter().order_by().first.return_value = None
            else:
                mock_q.filter().all.return_value = []
                mock_q.filter().first.return_value = self.mock_portfolio
            return mock_q

        self.db.query.side_effect = query_side_effect

        service = MentorService(
            fifo_reconstructor=mock_fifo,
            analytics_engine=mock_analytics,
            rule_engine=mock_rule_engine,
            prioritizer=mock_prioritizer,
            mentor_generator=mock_generator,
        )

        review = service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertEqual(review.user_id, 1)
        self.assertEqual(review.summary.trading_health_score, 90.0)
        self.assertEqual(review.coaching_response.headline, "Great Job")

        mock_fifo.process_trades.assert_called_once()
        mock_analytics.calculate_metrics.assert_called_once()
        mock_rule_engine.evaluate_all.assert_called_once()
        mock_prioritizer.prioritize.assert_called_once()
        mock_generator.generate.assert_called_once_with(mock_summary)

    def test_cache_hit_returns_persisted_review(self):
        """Test valid non-stale cached review returns directly from DB without calling generator."""
        summary = MentorSummary(
            trading_health_score=88.0,
            grade=TradingGrade.DISCIPLINED,
            portfolio_summary={},
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=[],
            improvement_focus="Discipline",
            all_insights=[],
        )
        response = MentorResponse(
            headline="Cached Headline",
            summary="Cached Summary",
            strengths=[],
            mistakes=[],
            risk_warning=None,
            action_items=[],
            motivation="Cached Motivation",
            next_focus="Discipline",
        )

        mock_review = MagicMock()
        mock_review.stale = False
        mock_review.trade_count = 2
        mock_review.last_trade_id = "102"
        mock_review.generated_at = datetime.now(timezone.utc)
        mock_review.summary_json = summary.model_dump()
        mock_review.response_json = response.model_dump()

        mock_trade = MagicMock()
        mock_trade.id = 102

        def query_side_effect(model):
            mock_q = MagicMock()
            if model == User:
                mock_q.filter().first.return_value = self.mock_user
            elif model == Trade:
                mock_q.filter().count.return_value = 2
                mock_q.filter().order_by().first.return_value = mock_trade
            elif model == MentorReview:
                mock_q.filter().order_by().first.return_value = mock_review
            return mock_q

        self.db.query.side_effect = query_side_effect

        mock_generator = MagicMock()
        service = MentorService(mentor_generator=mock_generator)

        review = service.generate_daily_review(self.db, user_id=1)

        self.assertEqual(review.coaching_response.headline, "Cached Headline")
        mock_generator.generate.assert_not_called()

    def test_mark_reviews_stale(self):
        """Test mark_reviews_stale updates stale flag for active user reviews."""
        service = MentorService()
        service.mark_reviews_stale(self.db, user_id=1)

        self.db.query().filter().update.assert_called_once_with({"stale": True})
        self.db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
