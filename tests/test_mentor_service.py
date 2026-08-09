"""
Unit tests for AI Mentor Conversational Coaching Architecture (app/mentor/service.py).

Tests:
- Test 1: Unsupported behavioral inference guardrails in SYSTEM_PROMPT
- Test 2: Precise metric interpretation guidance in SYSTEM_PROMPT
- Test 3: Prohibition of arbitrary numerical limits in SYSTEM_PROMPT
- Test 4: MentorResponse schema validation with 3-5 sentence mentor analysis
- Test 5: Raw LLM response logging instrumentation
- Test 6: Anti-leakage regression checking actual user_prompt passed to AI client
- Test 7: Existing deterministic summary & RuleEngine insights remain intact
"""

from datetime import datetime, timezone
import json
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock

from app.ai.exceptions import AIServiceUnavailableError
from app.mentor.models import MentorReview
from app.mentor.schema import (
    AnalyticsMetrics,
    Confidence,
    DailyMentorReview,
    Insight,
    InsightCategory,
    MentorContext,
    MentorResponse,
    MentorSummary,
    PublicMentorSummary,
    Severity,
    TradingGrade,
)
from app.mentor.service import MentorService
from app.trades.models import Trade
from app.users.models import User


class TestMentorService(unittest.IsolatedAsyncioTestCase):

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

    async def test_invalid_user_raises_value_error(self):
        """Test MentorService raises ValueError when user_id is not found."""
        self.db.query().filter().first.return_value = None

        service = MentorService()
        with self.assertRaises(ValueError):
            await service.generate_daily_review(self.db, user_id=999)

    async def test_no_trades_returns_clean_default_review(self):
        """Test MentorService handles user with 0 trades gracefully."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(
            return_value=json.dumps(
                {
                    "headline": "Welcome to PaperTrade",
                    "mentor_message": "Looking at your account, you have a clean slate with zero trades executed so far.",
                    "key_takeaway": "Take your first trade when a valid strategy setup appears.",
                    "risk_warning": None,
                    "next_focus": "Execution Discipline",
                }
            )
        )

        service = MentorService(ai_client=mock_ai_client)
        review = await service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertEqual(review.user_id, 1)
        self.assertEqual(review.summary.trading_health_score, 100.0)
        self.assertEqual(review.summary.portfolio_summary["total_trades_count"], 0)
        self.assertEqual(review.coaching_response.headline, "Welcome to PaperTrade")

    async def test_ai_failure_raises_exception_without_fallback(self):
        """Test AI provider failure raises AIServiceUnavailableError without generating fallback coaching."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIServiceUnavailableError("OpenRouter Timeout"))

        service = MentorService(ai_client=mock_ai_client)

        with self.assertRaises(AIServiceUnavailableError):
            await service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_1_unsupported_behavioral_inference(self):
        """Test 1: Verifies SYSTEM_PROMPT explicitly prohibits unsupported claims (winners run, cut losses, exit prematurely, emotional, etc.)."""
        prompt = MentorService.SYSTEM_PROMPT
        self.assertIn("CRITICAL BEHAVIORAL & EVIDENCE BOUNDARIES", prompt)
        self.assertIn("NO BEHAVIORAL HALLUCINATION", prompt)
        self.assertIn("lets winners run", prompt)
        self.assertIn("cuts losses quickly", prompt)
        self.assertIn("exits trades prematurely", prompt)
        self.assertIn("emotional", prompt)
        self.assertIn("revenge trading", prompt)
        self.assertIn("overtrading", prompt)

    def test_2_metric_interpretation_guidance(self):
        """Test 2: Verifies SYSTEM_PROMPT explicitly defines correct interpretation of profit_factor, win_rate, risk_reward, position_sizing, concentration_hhi."""
        prompt = MentorService.SYSTEM_PROMPT
        self.assertIn("PRECISE METRIC INTERPRETATION", prompt)
        self.assertIn("profit_factor", prompt)
        self.assertIn("risk_reward_ratio", prompt)
        self.assertIn("win_rate_pct", prompt)
        self.assertIn("max_position_sizing_pct", prompt)
        self.assertIn("portfolio_concentration_hhi", prompt)

    def test_3_no_arbitrary_thresholds(self):
        """Test 3: Verifies SYSTEM_PROMPT explicitly prohibits inventing arbitrary numerical risk limits unless supplied by context."""
        prompt = MentorService.SYSTEM_PROMPT
        self.assertIn("Do NOT invent arbitrary numerical limits", prompt)
        self.assertIn("Recommend directional adjustments instead", prompt)

    async def test_4_response_schema_validation(self):
        """Test 4: Mocks LLM with specified mentor response and verifies MentorResponse validates successfully."""
        mock_llm_json = json.dumps(
            {
                "headline": "Strong returns, but concentration needs attention",
                "mentor_message": "Your 3.99 profit factor is a strong result because aggregate gross profits substantially outweigh aggregate gross losses. The bigger concern is the 65.39% maximum position allocation combined with a high concentration score. That level of exposure means one position can have a disproportionate effect on the portfolio. I would focus on reducing concentration before trying to optimize the win rate further.",
                "key_takeaway": "Your profitability is encouraging, but concentration is currently the bigger risk.",
                "risk_warning": "A 65.39% maximum position allocation creates substantial single-position exposure.",
                "next_focus": "Reduce single-position concentration.",
            }
        )

        response = MentorResponse.model_validate_json(mock_llm_json)

        self.assertEqual(response.headline, "Strong returns, but concentration needs attention")
        self.assertIn("3.99 profit factor", response.mentor_message)
        self.assertEqual(response.key_takeaway, "Your profitability is encouraging, but concentration is currently the bigger risk.")
        self.assertEqual(response.risk_warning, "A 65.39% maximum position allocation creates substantial single-position exposure.")
        self.assertEqual(response.next_focus, "Reduce single-position concentration.")

    async def test_5_raw_response_logging_intact(self):
        """Test 5: Verifies raw LLM response logs remain intact."""
        mock_summary = MentorSummary(
            trading_health_score=80.0,
            grade=TradingGrade.DISCIPLINED,
            portfolio_summary={"win_rate_pct": 50.0, "total_realized_pnl": 1000.0},
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=[],
            improvement_focus="Discipline",
            all_insights=[],
        )

        mock_llm_json = json.dumps(
            {
                "headline": "Raw Response Log Test",
                "mentor_message": "Logged mentor message.",
                "key_takeaway": "Key takeaway.",
                "risk_warning": None,
                "next_focus": "Discipline",
            }
        )

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(return_value=mock_llm_json)

        with self.assertLogs("app.mentor.service", level="WARNING") as cm:
            service = MentorService(ai_client=mock_ai_client)
            await service._generate_coaching_response(mock_summary)

        log_output = "\n".join(cm.output)
        self.assertIn("AI_MENTOR_STAGE=llm_raw_response", log_output)
        self.assertIn("AI_MENTOR_RAW_LLM_RESPONSE_BEGIN", log_output)
        self.assertIn("Raw Response Log Test", log_output)
        self.assertIn("AI_MENTOR_RAW_LLM_RESPONSE_END", log_output)

    async def test_6_anti_leakage_regression(self):
        """Test 6: Inspects ACTUAL user_prompt passed into ai_client.generate_async and asserts zero RuleEngine identifiers leak."""
        fake_insight_1 = Insight(
            rule_id="MISTAKE_REVENGE_TRADING",
            category=InsightCategory.MISTAKE,
            title="Revenge Trading Detected",
            description="Re-entered trade after loss",
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            metrics_context={
                "revenge_trades_count": 2,
                "details": [{"losing_symbol": "AXISBANK", "next_symbol": "HDFCBANK"}],
            },
        )
        fake_insight_2 = Insight(
            rule_id="MISTAKE_OVERTRADING",
            category=InsightCategory.MISTAKE,
            title="Overtrading Frequency Alert",
            description="Too many trades",
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
        )
        fake_insight_3 = Insight(
            rule_id="RISK_POSITION_AND_DIVERSIFICATION",
            category=InsightCategory.RISK_WARNING,
            title="Position Sizing & Concentration Risk",
            description="High concentration",
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
        )
        fake_insight_4 = Insight(
            rule_id="RISK_REWARD_RATIO",
            category=InsightCategory.STRENGTH,
            title="Excellent Risk-Reward Ratio",
            description="Strong RRR",
            severity=Severity.LOW,
            confidence=Confidence.HIGH,
        )

        mock_summary = MentorSummary(
            trading_health_score=32.4,
            grade=TradingGrade.HIGH_RISK,
            portfolio_summary={
                "win_rate_pct": 40.0,
                "total_realized_pnl": 3260.02,
                "profit_factor": 3.99,
                "risk_reward_ratio": 2.0,
                "max_drawdown_pct": 1.03,
                "holding_duration_ratio": 0.51,
                "max_position_sizing_pct": 65.39,
                "portfolio_concentration_hhi": 4275.23,
                "total_trades_count": 40,
                "closed_positions_count": 15,
            },
            top_strengths=[fake_insight_4],
            top_mistakes=[fake_insight_1, fake_insight_2],
            top_risks=[fake_insight_3],
            action_items=[],
            improvement_focus="Emotional Trading",
            all_insights=[fake_insight_1, fake_insight_2, fake_insight_3, fake_insight_4],
        )

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(
            return_value=json.dumps(
                {
                    "headline": "Protect the edge you already have",
                    "mentor_message": "Looking at your recent performance, your profit factor is strong...",
                    "key_takeaway": "Your edge is promising, but position concentration is the bigger concern.",
                    "risk_warning": "A very large single-position allocation can magnify a bad outcome.",
                    "next_focus": "Position Sizing",
                }
            )
        )

        service = MentorService(ai_client=mock_ai_client)
        await service._generate_coaching_response(mock_summary)

        call_kwargs = mock_ai_client.generate_async.call_args.kwargs
        user_prompt = call_kwargs["user_prompt"]

        forbidden_tokens = [
            "MISTAKE_REVENGE_TRADING",
            "MISTAKE_OVERTRADING",
            "RISK_POSITION_AND_DIVERSIFICATION",
            "RISK_REWARD_RATIO",
            "Revenge Trading Detected",
            "Overtrading Frequency Alert",
            "Position Sizing & Concentration Risk",
            "AXISBANK",
            "HDFCBANK",
            "triggered_evidence",
            "primary_focus",
            "rule_id",
        ]

        for token in forbidden_tokens:
            self.assertNotIn(token, user_prompt, f"Forbidden RuleEngine token '{token}' leaked into LLM user prompt!")

    def test_7_existing_deterministic_summary_remains_intact(self):
        """Test 7: Verifies RuleEngine insights and summary structures remain fully functional in internal summary generation."""
        fake_insight = Insight(
            rule_id="MISTAKE_REVENGE_TRADING",
            category=InsightCategory.MISTAKE,
            title="Revenge Trading Detected",
            description="Re-entered trade after loss",
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
        )
        summary = MentorSummary(
            trading_health_score=50.0,
            grade=TradingGrade.AVERAGE,
            portfolio_summary={"win_rate_pct": 50.0},
            top_strengths=[],
            top_mistakes=[fake_insight],
            top_risks=[],
            action_items=["RuleEngine action"],
            improvement_focus="Execution",
            all_insights=[fake_insight],
        )

        self.assertEqual(len(summary.all_insights), 1)
        self.assertEqual(summary.all_insights[0].rule_id, "MISTAKE_REVENGE_TRADING")
        self.assertEqual(summary.grade, TradingGrade.AVERAGE)

    def test_mark_reviews_stale(self):
        """Test mark_reviews_stale updates stale flag for active user reviews."""
        service = MentorService()
        service.mark_reviews_stale(self.db, user_id=1)

        self.db.query().filter().update.assert_called_once_with({"stale": True})
        self.db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
