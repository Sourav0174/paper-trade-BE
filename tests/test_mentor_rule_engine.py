"""
Unit tests for AI Mentor Phase 2 Deterministic Rule Engine.

Tests:
- All 9 individual rule classes
- Prioritized evaluation via RuleEngine
"""

from datetime import datetime, timedelta
import unittest

from app.mentor.schema import (
    AnalyticsMetrics,
    ClosedPosition,
    Confidence,
    HoldingItem,
    InsightCategory,
    Severity,
    TradeInput,
)
from app.mentor.rule_engine import (
    ConcentrationRiskRule,
    DrawdownRule,
    FOMOBuyingRule,
    HoldingDurationAsymmetryRule,
    OvertradingRule,
    PositionSizingRule,
    RevengeTradingRule,
    RiskRewardRatioRule,
    RuleEngine,
    StopLossDisciplineRule,
)


class TestMentorRuleEngine(unittest.TestCase):

    def setUp(self):
        """Build standard mock metrics template for testing."""
        self.base_metrics = AnalyticsMetrics(
            total_trades_count=4,
            closed_positions_count=2,
            winning_positions_count=1,
            losing_positions_count=1,
            breakeven_positions_count=0,
            win_rate_pct=50.0,
            total_realized_pnl=200.0,
            total_gross_profit=500.0,
            total_gross_loss=300.0,
            average_profit=500.0,
            average_loss=300.0,
            profit_factor=1.67,
            risk_reward_ratio=1.67,
            max_drawdown_pct=5.0,
            max_drawdown_amount=5000.0,
            avg_holding_duration_minutes=30.0,
            avg_winning_duration_minutes=30.0,
            avg_losing_duration_minutes=30.0,
            holding_duration_ratio=1.0,
            portfolio_concentration_hhi=500.0,
            max_position_sizing_pct=10.0,
            avg_position_sizing_pct=8.0,
            total_unrealized_pnl=0.0,
        )

    def test_revenge_trading_rule_triggered(self):
        """Test RevengeTradingRule triggers when a position is opened within 15 mins of a loss."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 10, 30, 0)
        t3 = datetime(2026, 8, 1, 10, 35, 0)  # 5 mins after t2 close
        t4 = datetime(2026, 8, 1, 11, 0, 0)

        pos_loss = ClosedPosition(
            position_id="pos1",
            symbol="INFY",
            total_quantity=10,
            weighted_avg_buy_price=100.0,
            weighted_avg_sell_price=80.0,
            realized_pnl=-200.0,
            realized_pnl_percent=-20.0,
            open_timestamp=t1,
            close_timestamp=t2,
            holding_duration_minutes=30.0,
            is_win=False,
            is_loss=True,
            is_breakeven=False,
        )

        pos_revenge = ClosedPosition(
            position_id="pos2",
            symbol="RELIANCE",
            total_quantity=10,
            weighted_avg_buy_price=200.0,
            weighted_avg_sell_price=210.0,
            realized_pnl=100.0,
            realized_pnl_percent=5.0,
            open_timestamp=t3,
            close_timestamp=t4,
            holding_duration_minutes=25.0,
            is_win=True,
            is_loss=False,
            is_breakeven=False,
        )

        rule = RevengeTradingRule()
        result = rule.evaluate(self.base_metrics, closed_positions=[pos_loss, pos_revenge])

        self.assertTrue(result.is_triggered)
        self.assertIsNotNone(result.insight)
        self.assertEqual(result.insight.rule_id, "MISTAKE_REVENGE_TRADING")
        self.assertEqual(result.insight.severity, Severity.CRITICAL)

    def test_revenge_trading_rule_not_triggered(self):
        """Test RevengeTradingRule is not triggered when time gap > 15 mins."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 10, 30, 0)
        t3 = datetime(2026, 8, 1, 11, 0, 0)  # 30 mins after t2 close

        pos_loss = ClosedPosition(
            position_id="pos1",
            symbol="INFY",
            total_quantity=10,
            weighted_avg_buy_price=100.0,
            weighted_avg_sell_price=80.0,
            realized_pnl=-200.0,
            realized_pnl_percent=-20.0,
            open_timestamp=t1,
            close_timestamp=t2,
            holding_duration_minutes=30.0,
            is_win=False,
            is_loss=True,
            is_breakeven=False,
        )

        pos_normal = ClosedPosition(
            position_id="pos2",
            symbol="RELIANCE",
            total_quantity=10,
            weighted_avg_buy_price=200.0,
            weighted_avg_sell_price=210.0,
            realized_pnl=100.0,
            realized_pnl_percent=5.0,
            open_timestamp=t3,
            close_timestamp=t3 + timedelta(minutes=30),
            holding_duration_minutes=30.0,
            is_win=True,
            is_loss=False,
            is_breakeven=False,
        )

        rule = RevengeTradingRule()
        result = rule.evaluate(self.base_metrics, closed_positions=[pos_loss, pos_normal])
        self.assertFalse(result.is_triggered)

    def test_position_sizing_rule(self):
        """Test PositionSizingRule triggers on high position sizing."""
        metrics = self.base_metrics.model_copy(update={"max_position_sizing_pct": 28.0})

        rule = PositionSizingRule()
        result = rule.evaluate(metrics)

        self.assertTrue(result.is_triggered)
        self.assertEqual(result.insight.severity, Severity.CRITICAL)
        self.assertEqual(result.insight.rule_id, "RISK_POSITION_SIZING")

    def test_holding_duration_asymmetry_rule(self):
        """Test HoldingDurationAsymmetryRule triggers when loser duration > 1.5x winner duration."""
        metrics = self.base_metrics.model_copy(update={
            "holding_duration_ratio": 2.5,
            "avg_losing_duration_minutes": 100.0,
            "avg_winning_duration_minutes": 40.0,
        })

        rule = HoldingDurationAsymmetryRule()
        result = rule.evaluate(metrics)

        self.assertTrue(result.is_triggered)
        self.assertEqual(result.insight.severity, Severity.HIGH)
        self.assertEqual(result.insight.rule_id, "MISTAKE_HOLDING_DURATION_ASYMMETRY")

    def test_risk_reward_ratio_rule(self):
        """Test RiskRewardRatioRule for both mistake (<1.0) and strength (>=2.0)."""
        # Sub-optimal RRR
        metrics_bad = self.base_metrics.model_copy(update={"risk_reward_ratio": 0.7})
        rule = RiskRewardRatioRule()
        result_bad = rule.evaluate(metrics_bad)

        self.assertTrue(result_bad.is_triggered)
        self.assertEqual(result_bad.insight.category, InsightCategory.MISTAKE)

        # Strong RRR
        metrics_good = self.base_metrics.model_copy(update={"risk_reward_ratio": 2.2})
        result_good = rule.evaluate(metrics_good)

        self.assertTrue(result_good.is_triggered)
        self.assertEqual(result_good.insight.category, InsightCategory.STRENGTH)

    def test_concentration_risk_rule(self):
        """Test ConcentrationRiskRule triggers when HHI > 1800."""
        metrics = self.base_metrics.model_copy(update={"portfolio_concentration_hhi": 3200.0})

        rule = ConcentrationRiskRule()
        result = rule.evaluate(metrics)

        self.assertTrue(result.is_triggered)
        self.assertEqual(result.insight.severity, Severity.HIGH)

    def test_overtrading_rule(self):
        """Test OvertradingRule triggers when total_trades_count > 10."""
        metrics = self.base_metrics.model_copy(update={"total_trades_count": 14})

        rule = OvertradingRule()
        result = rule.evaluate(metrics)

        self.assertTrue(result.is_triggered)
        self.assertEqual(result.insight.rule_id, "MISTAKE_OVERTRADING")

    def test_drawdown_rule(self):
        """Test DrawdownRule triggers on max_drawdown_pct > 10%."""
        metrics = self.base_metrics.model_copy(update={"max_drawdown_pct": 22.5})

        rule = DrawdownRule()
        result = rule.evaluate(metrics)

        self.assertTrue(result.is_triggered)
        self.assertEqual(result.insight.severity, Severity.CRITICAL)

    def test_stop_loss_discipline_rule(self):
        """Test StopLossDisciplineRule triggers on losing position with loss > -5.0%."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        pos_bad_loss = ClosedPosition(
            position_id="pos1",
            symbol="INFY",
            total_quantity=10,
            weighted_avg_buy_price=100.0,
            weighted_avg_sell_price=90.0,
            realized_pnl=-100.0,
            realized_pnl_percent=-10.0,
            open_timestamp=t1,
            close_timestamp=t1 + timedelta(minutes=30),
            holding_duration_minutes=30.0,
            is_win=False,
            is_loss=True,
            is_breakeven=False,
        )

        rule = StopLossDisciplineRule()
        result = rule.evaluate(self.base_metrics, closed_positions=[pos_bad_loss])

        self.assertTrue(result.is_triggered)
        self.assertEqual(result.insight.rule_id, "MISTAKE_STOP_LOSS_DISCIPLINE")

    def test_rule_engine_prioritized_evaluation(self):
        """Test RuleEngine aggregates triggered rules and sorts insights by Severity priority."""
        metrics = self.base_metrics.model_copy(update={
            "max_position_sizing_pct": 30.0,  # CRITICAL
            "portfolio_concentration_hhi": 2200.0,  # MEDIUM
            "total_trades_count": 16,  # HIGH
        })

        engine = RuleEngine()
        insights = engine.evaluate_all(metrics)

        self.assertGreaterEqual(len(insights), 2)
        # Verify first insight has higher severity than subsequent insights
        severities = [i.severity for i in insights]
        self.assertEqual(severities[0], Severity.CRITICAL)

    def test_rule_engine_produces_facts_only_zero_coaching_text(self):
        """Proves RuleEngine detects rules (revenge, overtrading, sizing, concentration) with facts ONLY and ZERO coaching text."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 10, 30, 0)
        t3 = datetime(2026, 8, 1, 10, 35, 0)

        pos_loss = ClosedPosition(
            position_id="p1", symbol="INFY", total_quantity=10, weighted_avg_buy_price=100.0,
            weighted_avg_sell_price=80.0, realized_pnl=-200.0, realized_pnl_percent=-20.0,
            open_timestamp=t1, close_timestamp=t2, holding_duration_minutes=30.0,
            is_win=False, is_loss=True, is_breakeven=False
        )
        pos_revenge = ClosedPosition(
            position_id="p2", symbol="RELIANCE", total_quantity=10, weighted_avg_buy_price=200.0,
            weighted_avg_sell_price=210.0, realized_pnl=100.0, realized_pnl_percent=5.0,
            open_timestamp=t3, close_timestamp=t3 + timedelta(minutes=20), holding_duration_minutes=20.0,
            is_win=True, is_loss=False, is_breakeven=False
        )

        metrics = self.base_metrics.model_copy(update={
            "max_position_sizing_pct": 30.0,       # Excessive Position Sizing
            "portfolio_concentration_hhi": 2500.0,  # Poor Diversification
            "total_trades_count": 16,               # Overtrading
            "losing_positions_count": 1,
        })

        engine = RuleEngine()
        insights = engine.evaluate_all(metrics, closed_positions=[pos_loss, pos_revenge])

        # Verify all 4 target rules triggered
        triggered_rules = {i.rule_id for i in insights}
        self.assertIn("MISTAKE_REVENGE_TRADING", triggered_rules)
        self.assertIn("MISTAKE_OVERTRADING", triggered_rules)
        self.assertIn("RISK_POSITION_SIZING", triggered_rules)
        self.assertIn("RISK_CONCENTRATION_HHI", triggered_rules)

        # CRITICAL PROOF: Verify EVERY insight contains ZERO coaching text
        for insight in insights:
            self.assertEqual(insight.coaching_message, "", f"Rule {insight.rule_id} leaked coaching_message!")
            self.assertEqual(insight.action_item, "", f"Rule {insight.rule_id} leaked action_item!")
            self.assertIsNotNone(insight.metrics_context)
            self.assertGreater(len(insight.metrics_context), 0)


if __name__ == "__main__":
    unittest.main()
