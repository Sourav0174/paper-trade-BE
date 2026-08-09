"""
Unit tests for AI Mentor Phase 3C API Router Layer (app/mentor/router.py).

Tests:
- GET /mentor/daily-review
- GET /mentor/summary
- GET /mentor/trade-review/{trade_id}
- POST /mentor/regenerate
- Authentication and error status code mappings
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.mentor.schema import (
    DailyMentorReview,
    MentorResponse,
    MentorSummary,
    PublicMentorSummary,
    TradingGrade,
)
from app.mentor.service import mentor_service
from app.users.service import get_current_user


class TestMentorRouter(unittest.TestCase):

    def setUp(self):
        """Set up TestClient and authentication overrides for router tests."""
        self.mock_user = MagicMock()
        self.mock_user.id = 1
        self.mock_user.email = "test@example.com"

        app.dependency_overrides[get_current_user] = lambda: self.mock_user
        self.client = TestClient(app)

    def tearDown(self):
        """Clear dependency overrides after test run."""
        app.dependency_overrides.clear()

    @patch.object(mentor_service, "generate_daily_review", new_callable=AsyncMock)
    def test_get_daily_review_endpoint(self, mock_generate):
        """Test GET /mentor/daily-review returns 200 OK with DailyMentorReview."""
        summary = PublicMentorSummary(
            trading_health_score=90.0,
            portfolio_summary={"trading_health_score": 90.0},
        )
        coaching = MentorResponse(
            headline="Great Job",
            mentor_message="Disciplined execution observed across your trades.",
            key_takeaway="Maintain current risk discipline.",
            risk_warning=None,
            next_focus="Discipline",
        )

        mock_generate.return_value = DailyMentorReview(
            user_id=1,
            summary=summary,
            coaching_response=coaching,
        )

        res = self.client.get("/mentor/daily-review")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["user_id"], 1)
        self.assertEqual(data["summary"]["trading_health_score"], 90.0)
        self.assertEqual(data["coaching_response"]["headline"], "Great Job")

    @patch.object(mentor_service, "generate_summary")
    def test_get_summary_endpoint(self, mock_summary):
        """Test GET /mentor/summary returns 200 OK with MentorSummary."""
        mock_summary.return_value = MentorSummary(
            trading_health_score=85.0,
            grade=TradingGrade.DISCIPLINED,
            portfolio_summary={},
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=[],
            improvement_focus="Position Sizing",
            all_insights=[],
        )

        res = self.client.get("/mentor/summary")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["trading_health_score"], 85.0)
        self.assertEqual(data["grade"], "DISCIPLINED")

    @patch.object(mentor_service, "generate_trade_review", new_callable=AsyncMock)
    def test_get_trade_review_endpoint(self, mock_generate):
        """Test GET /mentor/trade-review/{trade_id} returns 200 OK with MentorResponse."""
        mock_generate.return_value = MentorResponse(
            headline="Trade Review",
            mentor_message="Good entry execution.",
            key_takeaway="Entry strategy aligned with plan.",
            risk_warning=None,
            next_focus="Discipline",
        )

        res = self.client.get("/mentor/trade-review/101")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["headline"], "Trade Review")

    @patch.object(mentor_service, "generate_trade_review", new_callable=AsyncMock)
    def test_get_trade_review_not_found(self, mock_generate):
        """Test GET /mentor/trade-review/{trade_id} returns 404 when trade is not found."""
        mock_generate.side_effect = ValueError("Trade with ID 999 not found")

        res = self.client.get("/mentor/trade-review/999")

        self.assertEqual(res.status_code, 404)
        data = res.json()
        self.assertIn("Trade with ID 999 not found", data["detail"])

    @patch.object(mentor_service, "generate_daily_review", new_callable=AsyncMock)
    def test_regenerate_endpoint(self, mock_generate):
        """Test POST /mentor/regenerate forces review generation."""
        summary = PublicMentorSummary(
            trading_health_score=95.0,
            portfolio_summary={"trading_health_score": 95.0},
        )
        coaching = MentorResponse(
            headline="Fresh Review",
            mentor_message="Regenerated coaching overview.",
            key_takeaway="Consistent execution.",
            risk_warning=None,
            next_focus="Discipline",
        )

        mock_generate.return_value = DailyMentorReview(
            user_id=1,
            summary=summary,
            coaching_response=coaching,
        )

        res = self.client.post("/mentor/regenerate")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["coaching_response"]["headline"], "Fresh Review")

    @patch.object(mentor_service, "generate_daily_review", new_callable=AsyncMock)
    def test_get_daily_review_ai_unavailable_returns_503(self, mock_generate):
        """Test GET /mentor/daily-review returns 503 when AI service is unavailable."""
        from app.ai.exceptions import AIServiceUnavailableError

        mock_generate.side_effect = AIServiceUnavailableError("OpenRouter Timeout")

        res = self.client.get("/mentor/daily-review")

        self.assertEqual(res.status_code, 503)
        data = res.json()
        self.assertIn("temporarily unavailable", data["detail"])

    @patch.object(mentor_service, "generate_daily_review", new_callable=AsyncMock)
    def test_get_daily_review_ai_rate_limit_returns_503(self, mock_generate):
        """Test GET /mentor/daily-review returns 503 when AI rate limit is hit."""
        from app.ai.exceptions import AIRateLimitError

        mock_generate.side_effect = AIRateLimitError("429 Rate limit")

        res = self.client.get("/mentor/daily-review")

        self.assertEqual(res.status_code, 503)
        data = res.json()
        self.assertIn("rate limited", data["detail"])

    @patch.object(mentor_service, "generate_daily_review", new_callable=AsyncMock)
    def test_get_daily_review_ai_parsing_error_returns_502(self, mock_generate):
        """Test GET /mentor/daily-review returns 502 when AI response validation fails."""
        from app.ai.exceptions import AIResponseParsingError

        mock_generate.side_effect = AIResponseParsingError("Invalid JSON schema")

        res = self.client.get("/mentor/daily-review")

        self.assertEqual(res.status_code, 502)
        data = res.json()
        self.assertIn("encountered an error", data["detail"])


if __name__ == "__main__":
    unittest.main()
