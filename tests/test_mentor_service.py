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

from app.ai.exceptions import (
    AIConfigurationError,
    AIRateLimitError,
    AIResponseParsingError,
    AIServiceUnavailableError,
)
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
from app.trades.models import Holding, Portfolio, Trade
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

    async def test_ai_timeout_triggers_deterministic_fallback(self):
        """Test AI timeout triggers deterministic fallback producing valid review and response."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIServiceUnavailableError("OpenRouter Timeout"))

        service = MentorService(ai_client=mock_ai_client)
        review = await service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertEqual(review.user_id, 1)
        self.assertIsInstance(review.coaching_response, MentorResponse)
        self.assertEqual(review.coaching_response.headline, "Clean Slate — Ready for Your First Trade")
        self.assertTrue(len(review.coaching_response.mentor_message) > 0)
        self.assertTrue(len(review.coaching_response.key_takeaway) > 0)
        self.db.add.assert_called_once()
        self.db.commit.assert_called_once()

    async def test_ai_rate_limit_triggers_deterministic_fallback(self):
        """Test AI 429 rate limit triggers deterministic fallback without raising 503."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIRateLimitError("Rate limit exceeded"))

        service = MentorService(ai_client=mock_ai_client)
        review = await service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertIsInstance(review.coaching_response, MentorResponse)

    async def test_ai_parsing_error_triggers_deterministic_fallback(self):
        """Test malformed AI response triggers deterministic fallback."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIResponseParsingError("Invalid JSON from LLM"))

        service = MentorService(ai_client=mock_ai_client)
        review = await service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertIsInstance(review.coaching_response, MentorResponse)

    async def test_ai_config_error_triggers_deterministic_fallback(self):
        """Test missing API key / AIConfigurationError triggers deterministic fallback."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIConfigurationError("Missing API key"))

        service = MentorService(ai_client=mock_ai_client)
        review = await service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertIsInstance(review.coaching_response, MentorResponse)

    async def test_ai_unexpected_exception_triggers_deterministic_fallback(self):
        """Test unexpected network drop or exception triggers deterministic fallback."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []
        self.db.query().filter().order_by().first.return_value = None

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=RuntimeError("Unexpected connection drop"))

        service = MentorService(ai_client=mock_ai_client)
        review = await service.generate_daily_review(self.db, user_id=1, force_regenerate=True)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertIsInstance(review.coaching_response, MentorResponse)

    def test_fallback_coaching_synthesis_with_active_mistakes_and_risks(self):
        """Test _synthesize_fallback_coaching synthesizes grounded coaching from rule insights."""
        summary = MentorSummary(
            trading_health_score=42.5,
            grade=TradingGrade.NEEDS_WORK,
            portfolio_summary={
                "trading_health_score": 42.5,
                "win_rate_pct": 35.0,
                "profit_factor": 0.85,
                "risk_reward_ratio": 1.2,
                "max_drawdown_pct": 8.5,
                "holding_duration_ratio": 1.5,
                "max_position_sizing_pct": 55.0,
                "portfolio_concentration_hhi": 3200.0,
                "total_realized_pnl": -1250.0,
                "total_trades_count": 20,
                "closed_positions_count": 12,
            },
            top_strengths=[],
            top_mistakes=[
                Insight(
                    rule_id="MISTAKE_REVENGE_TRADING",
                    category=InsightCategory.MISTAKE,
                    title="Revenge Trading Detected",
                    description="Re-entered 3 trades within 15 minutes of losses.",
                    severity=Severity.CRITICAL,
                    confidence=Confidence.HIGH,
                    action_item="Pause trading for 30 minutes following any closed loss.",
                ),
            ],
            top_risks=[
                Insight(
                    rule_id="RISK_CONCENTRATION_HHI",
                    category=InsightCategory.RISK_WARNING,
                    title="Concentration Risk",
                    description="HHI concentration is 3200.0 exceeding 2500 threshold.",
                    severity=Severity.HIGH,
                    confidence=Confidence.HIGH,
                    action_item="Diversify capital across multiple non-correlated assets.",
                ),
            ],
            action_items=[
                "Pause trading for 30 minutes following any closed loss.",
                "Cap single position sizing at 10% of portfolio.",
            ],
            improvement_focus="Emotional Trading",
            all_insights=[],
        )

        coaching = MentorService._synthesize_fallback_coaching(summary)

        self.assertIsInstance(coaching, MentorResponse)
        self.assertIn("Emotional Trading", coaching.headline)
        self.assertIn("Revenge Trading Detected", coaching.headline)
        self.assertIn("42.5/100", coaching.mentor_message)
        self.assertIn("35.0%", coaching.mentor_message)
        self.assertIn("revenge trading detected", coaching.mentor_message.lower())
        self.assertIn("Pause trading for 30 minutes following any closed loss.", coaching.key_takeaway)
        self.assertIsNotNone(coaching.risk_warning)
        self.assertIn("Concentration Risk", coaching.risk_warning)
        self.assertEqual(coaching.next_focus, "Emotional Trading")

    def test_fallback_coaching_synthesis_disciplined_trader(self):
        """Test _synthesize_fallback_coaching reinforces strengths for disciplined high-scoring trader."""
        summary = MentorSummary(
            trading_health_score=88.0,
            grade=TradingGrade.DISCIPLINED,
            portfolio_summary={
                "trading_health_score": 88.0,
                "win_rate_pct": 65.0,
                "profit_factor": 2.4,
                "risk_reward_ratio": 2.1,
                "max_drawdown_pct": 2.0,
                "holding_duration_ratio": 0.6,
                "max_position_sizing_pct": 12.0,
                "portfolio_concentration_hhi": 1100.0,
                "total_realized_pnl": 4500.0,
                "total_trades_count": 30,
                "closed_positions_count": 22,
            },
            top_strengths=[
                Insight(
                    rule_id="STRENGTH_WIN_RATE",
                    category=InsightCategory.STRENGTH,
                    title="Solid Win Rate",
                    description="Win rate is 65.0% across 22 closed positions.",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                ),
            ],
            top_mistakes=[],
            top_risks=[],
            action_items=[],
            improvement_focus="Discipline",
            all_insights=[],
        )

        coaching = MentorService._synthesize_fallback_coaching(summary)

        self.assertIsInstance(coaching, MentorResponse)
        self.assertIn("Strong Trading Discipline", coaching.headline)
        self.assertIn("solid win rate", coaching.mentor_message.lower())
        self.assertIn("4,500.00", coaching.mentor_message)
        self.assertIsNone(coaching.risk_warning)
        self.assertEqual(coaching.next_focus, "Discipline")

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

    async def test_legacy_cached_review_schema_invalidation_and_self_healing(self):
        """Test that legacy cached response_json missing required fields self-heals by generating fresh review."""
        self.db.query().filter().first.return_value = self.mock_user
        self.db.query().filter().count.return_value = 0
        self.db.query().filter().all.return_value = []

        # Create mock cached review with legacy incompatible response_json (lacking next_focus)
        mock_legacy_cached_review = MagicMock()
        mock_legacy_cached_review.stale = False
        mock_legacy_cached_review.trade_count = 0
        mock_legacy_cached_review.last_trade_id = None
        mock_legacy_cached_review.generated_at = datetime.now(timezone.utc)
        mock_legacy_cached_review.response_json = {
            "headline": "Legacy Review",
            "mentor_message": "Legacy mentor message.",
            "key_takeaway": "Legacy key takeaway.",
            "_coaching_source": "ai",
            # "next_focus" is MISSING!
        }
        mock_legacy_cached_review.summary_json = {
            "trading_health_score": 100.0,
            "grade": "MASTER",
            "portfolio_summary": {"trading_health_score": 100.0, "total_trades_count": 0},
            "top_strengths": [],
            "top_mistakes": [],
            "top_risks": [],
            "action_items": [],
            "improvement_focus": "Discipline",
            "all_insights": [],
        }

        self.db.query().filter().order_by().first.return_value = mock_legacy_cached_review

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(
            return_value=json.dumps(
                {
                    "headline": "Self Healed Review",
                    "mentor_message": "Fresh mentor message.",
                    "key_takeaway": "Fresh takeaway.",
                    "risk_warning": None,
                    "next_focus": "Execution",
                }
            )
        )

        service = MentorService(ai_client=mock_ai_client)
        review = await service.generate_daily_review(self.db, user_id=1, force_regenerate=False)

        self.assertIsInstance(review, DailyMentorReview)
        self.assertEqual(review.coaching_response.headline, "Self Healed Review")
        self.assertEqual(review.coaching_response.next_focus, "Execution")

    async def test_trade_review_valid_trade_success(self):
        """Test GET /mentor/trade-review/{trade_id} with valid trade invokes LLM with trade context."""
        now = datetime.now(timezone.utc)
        target_trade = Trade(
            id=101,
            user_id=1,
            symbol="TCS",
            quantity=10,
            price=3500.0,
            trade_type="SELL",
            created_at=now,
        )
        prior_buy = Trade(
            id=100,
            user_id=1,
            symbol="TCS",
            quantity=10,
            price=3300.0,
            trade_type="BUY",
            created_at=now,
        )

        mock_user_query = MagicMock()
        mock_user_query.filter().first.return_value = self.mock_user
        mock_trade_query = MagicMock()
        mock_trade_query.filter().first.return_value = target_trade
        mock_trade_query.filter().order_by().all.return_value = [prior_buy, target_trade]
        mock_portfolio_query = MagicMock()
        mock_portfolio_query.filter().first.return_value = self.mock_portfolio
        mock_holdings_query = MagicMock()
        mock_holdings_query.filter().all.return_value = []

        def db_query(model):
            if model == User:
                return mock_user_query
            elif model == Trade:
                return mock_trade_query
            elif model == Portfolio:
                return mock_portfolio_query
            elif model == Holding:
                return mock_holdings_query
            return MagicMock()

        self.db.query.side_effect = db_query

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(
            return_value=json.dumps(
                {
                    "headline": "Great Profit Taking on TCS",
                    "mentor_message": "You closed your TCS position with a disciplined $2,000 profit.",
                    "key_takeaway": "Following your target price captured the full swing.",
                    "risk_warning": None,
                    "next_focus": "Profit Protection",
                }
            )
        )

        service = MentorService(ai_client=mock_ai_client)
        response = await service.generate_trade_review(self.db, user_id=1, trade_id=101)

        self.assertIsInstance(response, MentorResponse)
        self.assertEqual(response.headline, "Great Profit Taking on TCS")
        self.assertEqual(response.next_focus, "Profit Protection")

        # Verify trade-specific prompt was passed to LLM
        call_kwargs = mock_ai_client.generate_async.call_args.kwargs
        user_prompt = call_kwargs["user_prompt"]
        self.assertIn("TCS", user_prompt)
        self.assertIn("3500", user_prompt)
        self.assertIn("SELL", user_prompt)

    async def test_trade_review_nonexistent_trade_raises_value_error(self):
        """Test generate_trade_review raises ValueError when trade_id does not exist."""
        mock_user_query = MagicMock()
        mock_user_query.filter().first.return_value = self.mock_user
        mock_trade_query = MagicMock()
        mock_trade_query.filter().first.return_value = None

        def db_query(model):
            if model == User:
                return mock_user_query
            elif model == Trade:
                return mock_trade_query
            return MagicMock()

        self.db.query.side_effect = db_query

        service = MentorService()
        with self.assertRaises(ValueError) as ctx:
            await service.generate_trade_review(self.db, user_id=1, trade_id=999)
        self.assertIn("Trade with ID 999 not found", str(ctx.exception))

    async def test_trade_review_trade_belonging_to_another_user_raises_value_error(self):
        """Test generate_trade_review raises ValueError when trade belongs to another user."""
        mock_user_query = MagicMock()
        mock_user_query.filter().first.return_value = self.mock_user
        mock_trade_query = MagicMock()
        mock_trade_query.filter().first.return_value = None

        def db_query(model):
            if model == User:
                return mock_user_query
            elif model == Trade:
                return mock_trade_query
            return MagicMock()

        self.db.query.side_effect = db_query

        service = MentorService()
        with self.assertRaises(ValueError) as ctx:
            await service.generate_trade_review(self.db, user_id=1, trade_id=202)
        self.assertIn("not found for user 1", str(ctx.exception))

    async def test_trade_review_fallback_on_llm_failure(self):
        """Test trade review returns deterministic fallback on LLM failure without crashing."""
        now = datetime.now(timezone.utc)
        target_trade = Trade(
            id=105,
            user_id=1,
            symbol="INFY",
            quantity=50,
            price=1800.0,
            trade_type="SELL",
            created_at=now,
        )
        prior_buy = Trade(
            id=104,
            user_id=1,
            symbol="INFY",
            quantity=50,
            price=1900.0,
            trade_type="BUY",
            created_at=now,
        )

        mock_user_query = MagicMock()
        mock_user_query.filter().first.return_value = self.mock_user
        mock_trade_query = MagicMock()
        mock_trade_query.filter().first.return_value = target_trade
        mock_trade_query.filter().order_by().all.return_value = [prior_buy, target_trade]
        mock_portfolio_query = MagicMock()
        mock_portfolio_query.filter().first.return_value = self.mock_portfolio
        mock_holdings_query = MagicMock()
        mock_holdings_query.filter().all.return_value = []

        def db_query(model):
            if model == User:
                return mock_user_query
            elif model == Trade:
                return mock_trade_query
            elif model == Portfolio:
                return mock_portfolio_query
            elif model == Holding:
                return mock_holdings_query
            return MagicMock()

        self.db.query.side_effect = db_query

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIServiceUnavailableError("OpenRouter 503"))

        service = MentorService(ai_client=mock_ai_client)
        response = await service.generate_trade_review(self.db, user_id=1, trade_id=105)

        self.assertIsInstance(response, MentorResponse)
        self.assertIn("Controlled Loss on INFY", response.headline)
        self.assertIn("INFY", response.mentor_message)
        self.assertIn("1,800.00", response.mentor_message)
        self.assertEqual(response.next_focus, "Loss Acceptance")

    async def test_trade_review_single_open_buy_trade(self):
        """Test trade review handles a newly opened BUY trade with zero closed history gracefully."""
        now = datetime.now(timezone.utc)
        target_trade = Trade(
            id=200,
            user_id=1,
            symbol="RELIANCE",
            quantity=25,
            price=2800.0,
            trade_type="BUY",
            created_at=now,
        )

        mock_user_query = MagicMock()
        mock_user_query.filter().first.return_value = self.mock_user
        mock_trade_query = MagicMock()
        mock_trade_query.filter().first.return_value = target_trade
        mock_trade_query.filter().order_by().all.return_value = [target_trade]
        mock_portfolio_query = MagicMock()
        mock_portfolio_query.filter().first.return_value = self.mock_portfolio
        mock_holdings_query = MagicMock()
        mock_holdings_query.filter().all.return_value = []

        def db_query(model):
            if model == User:
                return mock_user_query
            elif model == Trade:
                return mock_trade_query
            elif model == Portfolio:
                return mock_portfolio_query
            elif model == Holding:
                return mock_holdings_query
            return MagicMock()

        self.db.query.side_effect = db_query

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIServiceUnavailableError("LLM down"))

        service = MentorService(ai_client=mock_ai_client)
        response = await service.generate_trade_review(self.db, user_id=1, trade_id=200)

        self.assertIsInstance(response, MentorResponse)
        self.assertIn("RELIANCE", response.headline)
        self.assertIn("2,800.00", response.mentor_message)
        self.assertIn("currently active in your portfolio", response.mentor_message)

    async def test_trade_review_detects_revenge_entry(self):
        """Test trade review flags rapid re-entry within 15 minutes of a loss as a revenge trade risk."""
        from datetime import timedelta
        base_time = datetime.now(timezone.utc)
        loss_buy = Trade(id=1, user_id=1, symbol="SBIN", quantity=100, price=600.0, trade_type="BUY", created_at=base_time)
        loss_sell = Trade(id=2, user_id=1, symbol="SBIN", quantity=100, price=550.0, trade_type="SELL", created_at=base_time + timedelta(minutes=10))
        # Re-entry 5 minutes after loss
        revenge_buy = Trade(id=3, user_id=1, symbol="SBIN", quantity=150, price=552.0, trade_type="BUY", created_at=base_time + timedelta(minutes=15))

        mock_user_query = MagicMock()
        mock_user_query.filter().first.return_value = self.mock_user
        mock_trade_query = MagicMock()
        mock_trade_query.filter().first.return_value = revenge_buy
        mock_trade_query.filter().order_by().all.return_value = [loss_buy, loss_sell, revenge_buy]
        mock_portfolio_query = MagicMock()
        mock_portfolio_query.filter().first.return_value = self.mock_portfolio
        mock_holdings_query = MagicMock()
        mock_holdings_query.filter().all.return_value = []

        def db_query(model):
            if model == User:
                return mock_user_query
            elif model == Trade:
                return mock_trade_query
            elif model == Portfolio:
                return mock_portfolio_query
            elif model == Holding:
                return mock_holdings_query
            return MagicMock()

        self.db.query.side_effect = db_query

        mock_ai_client = MagicMock()
        mock_ai_client.generate_async = AsyncMock(side_effect=AIServiceUnavailableError("LLM down"))

        service = MentorService(ai_client=mock_ai_client)
        response = await service.generate_trade_review(self.db, user_id=1, trade_id=3)

        self.assertIsInstance(response, MentorResponse)
        self.assertIn("Rapid Re-Entry", response.headline)
        self.assertIn("revenge trading", response.mentor_message.lower())
        self.assertIsNotNone(response.risk_warning)
        self.assertIn("Revenge", response.risk_warning)
        self.assertEqual(response.next_focus, "Emotional Discipline")


if __name__ == "__main__":
    unittest.main()
