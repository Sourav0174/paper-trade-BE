"""
Unit tests for AI Mentor Phase 3A AI Generation Layer.

Tests:
- PromptBuilder (PromptContext generation & guardrails)
- TemplateGenerator (Deterministic fallback response generation)
- ResponseValidator (Guardrail validation & violation detection)
- MentorGenerator & GeminiGenerator (Pipeline & fallback execution)
"""

import json
import unittest

from app.mentor.schema import (
    AnalyticsMetrics,
    Confidence,
    Insight,
    InsightCategory,
    MentorResponse,
    MentorSummary,
    Severity,
    TradingGrade,
)
from app.mentor.prompt_builder import PromptBuilder
from app.mentor.template_generator import TemplateGenerator
from app.mentor.response_validator import ResponseValidator
from app.mentor.mentor_generator import GeminiGenerator, MentorGenerator


class TestMentorAILayer(unittest.TestCase):

    def setUp(self):
        """Set up standard summary fixture for AI layer tests."""
        self.metrics = AnalyticsMetrics(
            total_trades_count=6,
            closed_positions_count=4,
            winning_positions_count=3,
            losing_positions_count=1,
            breakeven_positions_count=0,
            win_rate_pct=75.0,
            total_realized_pnl=2500.0,
            total_gross_profit=3000.0,
            total_gross_loss=500.0,
            average_profit=1000.0,
            average_loss=500.0,
            profit_factor=6.0,
            risk_reward_ratio=2.0,
            max_drawdown_pct=3.0,
            max_drawdown_amount=1500.0,
            avg_holding_duration_minutes=40.0,
            avg_winning_duration_minutes=35.0,
            avg_losing_duration_minutes=55.0,
            holding_duration_ratio=1.57,
            portfolio_concentration_hhi=800.0,
            max_position_sizing_pct=12.0,
            avg_position_sizing_pct=10.0,
            total_unrealized_pnl=0.0,
        )

        self.summary = MentorSummary(
            trading_health_score=82.5,
            grade=TradingGrade.DISCIPLINED,
            portfolio_summary={
                "trading_health_score": 82.5,
                "win_rate_pct": 75.0,
                "total_realized_pnl": 2500.0,
                "closed_positions_count": 4,
            },
            top_strengths=[
                Insight(
                    rule_id="RISK_REWARD_RATIO",
                    category=InsightCategory.STRENGTH,
                    title="Excellent Risk-Reward Ratio",
                    description="Maintained RRR of 2.0.",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    coaching_message="Maintain current entry discipline.",
                    action_item="Target trades with at least 1.5x upside.",
                )
            ],
            top_mistakes=[
                Insight(
                    rule_id="MISTAKE_HOLDING_DURATION_ASYMMETRY",
                    category=InsightCategory.MISTAKE,
                    title="Holding Losers Too Long",
                    description="Losers held 1.57x longer.",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    coaching_message="Cut losses faster.",
                    action_item="Set a hard time-stop on trades.",
                )
            ],
            top_risks=[],
            action_items=["Target trades with at least 1.5x upside.", "Set a hard time-stop on trades."],
            improvement_focus="Discipline",
            all_insights=[],
        )

    def test_prompt_builder(self):
        """Test PromptBuilder constructs decoupled system and user prompt strings."""
        context = PromptBuilder.build_prompt_context(self.summary)

        self.assertIn("NEVER PREDICT FUTURE STOCK PRICES", context.system_prompt)
        self.assertIn("NEVER RECOMMEND BUYING, SELLING, OR HOLDING", context.system_prompt)
        self.assertIn("Discipline", context.user_prompt)

        # Verify user prompt includes valid JSON payload
        json_start = context.user_prompt.find("{")
        payload = json.loads(context.user_prompt[json_start:])
        self.assertEqual(payload["health_score"], 82.5)
        self.assertEqual(payload["grade"], "DISCIPLINED")

    def test_template_generator(self):
        """Test TemplateGenerator creates valid structured MentorResponse without external calls."""
        response = TemplateGenerator.generate_response(self.summary)

        self.assertIsInstance(response, MentorResponse)
        self.assertEqual(response.headline, "Solid Performance & Disciplined Execution")
        self.assertIn("82.5", response.summary)
        self.assertEqual(len(response.strengths), 1)
        self.assertEqual(len(response.mistakes), 1)
        self.assertIsNone(response.risk_warning)
        self.assertEqual(response.next_focus, "Discipline")

    def test_response_validator_valid_response(self):
        """Test ResponseValidator approves compliant mentor response."""
        response = TemplateGenerator.generate_response(self.summary)
        result = ResponseValidator.validate(response)

        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.violations), 0)

    def test_response_validator_buy_recommendation_rejection(self):
        """Test ResponseValidator rejects responses containing buy recommendations."""
        bad_response = MentorResponse(
            headline="Good Job",
            summary="You should buy RELIANCE stock immediately for quick profits.",
            strengths=[],
            mistakes=[],
            risk_warning=None,
            action_items=[],
            motivation="Keep trading.",
            next_focus="Discipline",
        )

        result = ResponseValidator.validate(bad_response)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Buy recommendation" in v for v in result.violations))

    def test_response_validator_price_prediction_rejection(self):
        """Test ResponseValidator rejects responses containing price predictions."""
        bad_response = MentorResponse(
            headline="Target Reached",
            summary="The stock price target will reach 3500 next week.",
            strengths=[],
            mistakes=[],
            risk_warning=None,
            action_items=[],
            motivation="Stay invested.",
            next_focus="Discipline",
        )

        result = ResponseValidator.validate(bad_response)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Price prediction" in v for v in result.violations))

    def test_response_validator_profit_guarantee_rejection(self):
        """Test ResponseValidator rejects responses promising guaranteed profits."""
        bad_response = MentorResponse(
            headline="Guaranteed Strategy",
            summary="This strategy yields a guaranteed profit of 50%.",
            strengths=[],
            mistakes=[],
            risk_warning=None,
            action_items=[],
            motivation="Win every trade.",
            next_focus="Discipline",
        )

        result = ResponseValidator.validate(bad_response)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Profit guarantee" in v for v in result.violations))

    def test_mentor_generator_unconfigured_api_fallback(self):
        """Test MentorGenerator seamlessly falls back to TemplateGenerator when API key is unconfigured."""
        generator = GeminiGenerator(api_key=None)
        orchestrator = MentorGenerator(generator=generator)

        response = orchestrator.generate(self.summary)
        self.assertIsInstance(response, MentorResponse)
        self.assertEqual(response.headline, "Solid Performance & Disciplined Execution")


if __name__ == "__main__":
    unittest.main()
