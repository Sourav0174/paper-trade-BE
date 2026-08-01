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
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.mentor.schema import (
    DailyMentorReview,
    MentorResponse,
    MentorSummary,
    TradingGrade,
)
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

    @patch("app.mentor.router.mentor_service")
    def test_get_daily_review_endpoint(self, mock_service):
        """Test GET /mentor/daily-review returns 200 OK with DailyMentorReview."""
        summary = MentorSummary(
            trading_health_score=90.0,
            grade=TradingGrade.MASTER,
            portfolio_summary={},
            top_strengths=[],
            top_mistakes=[],
            top_risks=[],
            action_items=[],
            improvement_focus="Discipline",
            all_insights=[],
        )
        coaching = MentorResponse(
            headline="Great Job",
            summary="Disciplined trading.",
            strengths=[],
            mistakes=[],
            risk_warning=None,
            action_items=[],
            motivation="Keep going.",
            next_focus="Discipline",
        )

        mock_service.generate_daily_review.return_value = DailyMentorReview(
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

    @patch("app.mentor.router.mentor_service")
    def test_get_summary_endpoint(self, mock_service):
        """Test GET /mentor/summary returns 200 OK with MentorSummary."""
        mock_service.generate_summary.return_value = MentorSummary(
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

    @patch("app.mentor.router.mentor_service")
    def test_get_trade_review_endpoint(self, mock_service):
        """Test GET /mentor/trade-review/{trade_id} returns 200 OK with MentorResponse."""
        mock_service.generate_trade_review.return_value = MentorResponse(
            headline="Trade Review",
            summary="Good entry.",
            strengths=[],
            mistakes=[],
            risk_warning=None,
            action_items=[],
            motivation="Stay disciplined.",
            next_focus="Discipline",
        )

        res = self.client.get("/mentor/trade-review/101")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["headline"], "Trade Review")

    @patch("app.mentor.router.mentor_service")
    def test_get_trade_review_not_found(self, mock_service):
        """Test GET /mentor/trade-review/{trade_id} returns 404 when trade is not found."""
        mock_service.generate_trade_review.side_effect = ValueError("Trade with ID 999 not found")

        res = self.client.get("/mentor/trade-review/999")

        self.assertEqual(res.status_code, 404)
        data = res.json()
        self.assertIn("Trade with ID 999 not found", data["detail"])

    @patch("app.mentor.router.mentor_service")
    def test_regenerate_endpoint(self, mock_service):
        """Test POST /mentor/regenerate forces review generation."""
        summary = MentorSummary(
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
        coaching = MentorResponse(
            headline="Fresh Review",
            summary="Regenerated overview.",
            strengths=[],
            mistakes=[],
            risk_warning=None,
            action_items=[],
            motivation="Keep it up.",
            next_focus="Discipline",
        )

        mock_service.generate_daily_review.return_value = DailyMentorReview(
            user_id=1,
            summary=summary,
            coaching_response=coaching,
        )

        res = self.client.post("/mentor/regenerate")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["coaching_response"]["headline"], "Fresh Review")


if __name__ == "__main__":
    unittest.main()
