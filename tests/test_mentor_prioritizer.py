"""
Unit tests for AI Mentor Phase 2.5 Insight Prioritizer & Mentor Summary.

Tests:
- Prioritization and insight ranking
- Duplicate / related insight merging
- Health score and TradingGrade calculation
- Single primary improvement focus selection
- Action item extraction
"""

import unittest

from app.mentor.schema import (
    AnalyticsMetrics,
    Confidence,
    Insight,
    InsightCategory,
    Severity,
    TradingGrade,
)
from app.mentor.prioritizer import InsightPrioritizer


class TestMentorPrioritizer(unittest.TestCase):

    def setUp(self):
        """Set up standard metrics fixture for prioritizer tests."""
        self.base_metrics = AnalyticsMetrics(
            total_trades_count=5,
            closed_positions_count=3,
            winning_positions_count=2,
            losing_positions_count=1,
            breakeven_positions_count=0,
            win_rate_pct=66.7,
            total_realized_pnl=1200.0,
            total_gross_profit=1500.0,
            total_gross_loss=300.0,
            average_profit=750.0,
            average_loss=300.0,
            profit_factor=5.0,
            risk_reward_ratio=2.5,
            max_drawdown_pct=4.0,
            max_drawdown_amount=2000.0,
            avg_holding_duration_minutes=45.0,
            avg_winning_duration_minutes=40.0,
            avg_losing_duration_minutes=55.0,
            holding_duration_ratio=1.38,
            portfolio_concentration_hhi=600.0,
            max_position_sizing_pct=10.0,
            avg_position_sizing_pct=8.0,
            total_unrealized_pnl=0.0,
        )

    def test_grade_calculation(self):
        """Test grade mapping across all health score threshold tiers."""
        self.assertEqual(InsightPrioritizer.calculate_grade(95.0), TradingGrade.MASTER)
        self.assertEqual(InsightPrioritizer.calculate_grade(85.0), TradingGrade.DISCIPLINED)
        self.assertEqual(InsightPrioritizer.calculate_grade(68.0), TradingGrade.AVERAGE)
        self.assertEqual(InsightPrioritizer.calculate_grade(50.0), TradingGrade.NEEDS_WORK)
        self.assertEqual(InsightPrioritizer.calculate_grade(30.0), TradingGrade.HIGH_RISK)

    def test_duplicate_merging(self):
        """Test merging of Position Sizing and Concentration Risk into a single unified insight."""
        sizing_insight = Insight(
            rule_id="RISK_POSITION_SIZING",
            category=InsightCategory.RISK_WARNING,
            title="Oversized Position Allocation",
            description="Single position reached 22% of capital.",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            metrics_context={"max_position_sizing_pct": 22.0},
            coaching_message="Limit allocation per stock.",
            action_item="Reduce maximum position size below 15%.",
        )

        hhi_insight = Insight(
            rule_id="RISK_CONCENTRATION_HHI",
            category=InsightCategory.RISK_WARNING,
            title="High Portfolio Concentration",
            description="HHI index reached 2400.",
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            metrics_context={"portfolio_concentration_hhi": 2400.0},
            coaching_message="Diversify across sectors.",
            action_item="Spread capital across 4-6 sectors.",
        )

        merged = InsightPrioritizer._merge_related_insights([sizing_insight, hhi_insight])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].rule_id, "RISK_POSITION_AND_DIVERSIFICATION")
        self.assertEqual(merged[0].severity, Severity.HIGH)

    def test_improvement_focus_selection(self):
        """Test selecting exactly ONE primary improvement focus area."""
        # 1. Emotional Trading
        insight_revenge = Insight(
            rule_id="MISTAKE_REVENGE_TRADING",
            category=InsightCategory.MISTAKE,
            title="Revenge Trading",
            description="Re-entered after loss.",
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            coaching_message="Cool off.",
            action_item="Wait 15 mins.",
        )
        focus1 = InsightPrioritizer.determine_improvement_focus(self.base_metrics, [insight_revenge])
        self.assertEqual(focus1, "Emotional Trading")

        # 2. Risk Management
        insight_drawdown = Insight(
            rule_id="RISK_MAX_DRAWDOWN",
            category=InsightCategory.RISK_WARNING,
            title="Drawdown",
            description="Drawdown high.",
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            coaching_message="Reduce sizing.",
            action_item="Reduce sizing.",
        )
        focus2 = InsightPrioritizer.determine_improvement_focus(self.base_metrics, [insight_drawdown])
        self.assertEqual(focus2, "Risk Management")

        # 3. Position Sizing
        insight_sizing = Insight(
            rule_id="RISK_POSITION_SIZING",
            category=InsightCategory.RISK_WARNING,
            title="Sizing",
            description="Large sizing.",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            coaching_message="Cap sizing.",
            action_item="Cap sizing.",
        )
        focus3 = InsightPrioritizer.determine_improvement_focus(self.base_metrics, [insight_sizing])
        self.assertEqual(focus3, "Position Sizing")

    def test_action_item_generation(self):
        """Test extracting max 3 unique action items from prioritized insights."""
        i1 = Insight(
            rule_id="r1",
            category=InsightCategory.MISTAKE,
            title="t1",
            description="d1",
            severity=Severity.CRITICAL,
            confidence=Confidence.HIGH,
            coaching_message="c1",
            action_item="Action 1: Wait 15 mins after loss.",
        )

        i2 = Insight(
            rule_id="r2",
            category=InsightCategory.RISK_WARNING,
            title="t2",
            description="d2",
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            coaching_message="c2",
            action_item="Action 2: Limit allocation to 10%.",
        )

        i3 = Insight(
            rule_id="r3",
            category=InsightCategory.MISTAKE,
            title="t3",
            description="d3",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            coaching_message="c3",
            action_item="Action 3: Target 1.5 RRR.",
        )

        i4 = Insight(
            rule_id="r4",
            category=InsightCategory.HABIT,
            title="t4",
            description="d4",
            severity=Severity.LOW,
            confidence=Confidence.HIGH,
            coaching_message="c4",
            action_item="Action 4: Extra item.",
        )

        actions = InsightPrioritizer.generate_action_items([i1, i2, i3, i4])

        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0], "Action 1: Wait 15 mins after loss.")
        self.assertEqual(actions[1], "Action 2: Limit allocation to 10%.")
        self.assertEqual(actions[2], "Action 3: Target 1.5 RRR.")

    def test_prioritize_full_summary(self):
        """Test complete prioritize workflow generating a valid MentorSummary."""
        insight = Insight(
            rule_id="RISK_POSITION_SIZING",
            category=InsightCategory.RISK_WARNING,
            title="Oversized Position",
            description="Sizing at 18%.",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            coaching_message="Limit position size.",
            action_item="Cap position size at 10%.",
        )

        summary = InsightPrioritizer.prioritize(self.base_metrics, [insight])

        self.assertIsInstance(summary.trading_health_score, float)
        self.assertIn(summary.grade, list(TradingGrade))
        self.assertEqual(len(summary.action_items), 1)
        self.assertEqual(summary.improvement_focus, "Position Sizing")
        self.assertEqual(len(summary.top_risks), 1)


if __name__ == "__main__":
    unittest.main()
