"""
Unit tests for AI Infrastructure Layer (app/ai).

Tests:
- AISettings
- GeminiProvider exception handling with google-genai SDK
- AIClient provider delegation
- Decoupled MentorGenerator fallback execution
"""

import unittest
from unittest.mock import MagicMock, patch
from google.genai.errors import APIError

from app.ai import (
    AIClient,
    AIConfigurationError,
    AIException,
    AIRateLimitError,
    AIResponseParsingError,
    AIServiceUnavailableError,
    AISettings,
    GeminiProvider,
)
from app.mentor.mentor_generator import GeminiGenerator, MentorGenerator
from app.mentor.schema import AnalyticsMetrics, MentorSummary, TradingGrade


class TestAIInfrastructure(unittest.TestCase):

    def setUp(self):
        """Build standard summary fixture for tests."""
        self.metrics = AnalyticsMetrics(
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

        self.summary = MentorSummary(
            trading_health_score=95.0,
            grade=TradingGrade.MASTER,
            portfolio_summary={},
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=[],
            improvement_focus="Discipline",
            all_insights=[],
        )

    def test_ai_settings_effective_key(self):
        """Test AISettings property resolves GEMINI_API_KEY or GOOGLE_API_KEY."""
        settings = AISettings(GEMINI_API_KEY=None, GOOGLE_API_KEY="test-google-key")
        self.assertEqual(settings.effective_gemini_api_key, "test-google-key")

    def test_gemini_provider_missing_key_raises_config_error(self):
        """Test GeminiProvider raises AIConfigurationError when key is missing."""
        provider = GeminiProvider(api_key=None, settings=AISettings(GEMINI_API_KEY=None, GOOGLE_API_KEY=None))
        with self.assertRaises(AIConfigurationError):
            provider.generate(system_prompt="sys", user_prompt="usr")

    @patch("google.genai.Client")
    def test_gemini_provider_rate_limit(self, mock_client_cls):
        """Test GeminiProvider maps APIError with status 429 / quota to AIRateLimitError."""
        mock_client = MagicMock()
        mock_err = APIError(code=429, response_json={"error": {"message": "RESOURCE_EXHAUSTED: quota exceeded"}})
        mock_client.models.generate_content.side_effect = mock_err
        mock_client_cls.return_value = mock_client

        provider = GeminiProvider(api_key="valid-key")
        with self.assertRaises(AIRateLimitError):
            provider.generate(system_prompt="sys", user_prompt="usr")

    @patch("google.genai.Client")
    def test_gemini_provider_success(self, mock_client_cls):
        """Test GeminiProvider parses valid google-genai SDK response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"headline": "Success"}'
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        provider = GeminiProvider(api_key="valid-key")
        output = provider.generate(system_prompt="sys", user_prompt="usr")
        self.assertEqual(output, '{"headline": "Success"}')

    def test_ai_client_delegation(self):
        """Test AIClient delegates generate call to underlying provider."""
        mock_provider = MagicMock()
        mock_provider.generate.return_value = "raw response"

        client = AIClient(provider=mock_provider)
        res = client.generate("sys", "usr")

        self.assertEqual(res, "raw response")
        mock_provider.generate.assert_called_once_with(
            system_prompt="sys",
            user_prompt="usr",
            response_mime_type="application/json",
        )

    def test_mentor_generator_fallback_on_ai_exception(self):
        """Test MentorGenerator falls back to TemplateGenerator when AIClient raises AIException."""
        mock_client = MagicMock()
        mock_client.generate.side_effect = AIConfigurationError("Key missing")

        gemini_gen = GeminiGenerator(ai_client=mock_client)
        orchestrator = MentorGenerator(generator=gemini_gen)

        response = orchestrator.generate(self.summary)
        self.assertEqual(response.headline, "Outstanding Execution & Masterful Discipline!")


if __name__ == "__main__":
    unittest.main()
