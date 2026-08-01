"""
Unit tests for AI Mentor Phase 1 Analytics Foundation.

Tests:
1. FIFO Position Reconstruction Engine (FIFOReconstructor)
2. Deterministic Analytics Engine (AnalyticsEngine)
"""

from datetime import datetime, timedelta
import unittest

from app.mentor.schema import (
    AnalyticsMetrics,
    ClosedPosition,
    ClosedTradeChunk,
    FifoReconstructionResult,
    HoldingItem,
    TradeInput,
)
from app.mentor.fifo import FIFOReconstructor
from app.mentor.analytics import AnalyticsEngine


class TestMentorAnalytics(unittest.TestCase):

    def test_fifo_simple_buy_and_sell(self):
        """Test simple single BUY and single SELL execution."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 11, 0, 0)

        trades = [
            TradeInput(id=1, symbol="RELIANCE", quantity=10, price=2000.0, trade_type="BUY", created_at=t1),
            TradeInput(id=2, symbol="RELIANCE", quantity=10, price=2200.0, trade_type="SELL", created_at=t2),
        ]

        result = FIFOReconstructor.process_trades(trades)

        self.assertEqual(len(result.closed_positions), 1)
        self.assertEqual(len(result.closed_chunks), 1)
        self.assertEqual(len(result.open_positions), 0)
        self.assertEqual(len(result.unmatched_sells), 0)

        pos = result.closed_positions[0]
        self.assertEqual(pos.symbol, "RELIANCE")
        self.assertEqual(pos.total_quantity, 10)
        self.assertEqual(pos.weighted_avg_buy_price, 2000.0)
        self.assertEqual(pos.weighted_avg_sell_price, 2200.0)
        self.assertEqual(pos.realized_pnl, 2000.0)  # (2200 - 2000) * 10
        self.assertEqual(pos.realized_pnl_percent, 10.0)
        self.assertTrue(pos.is_win)
        self.assertEqual(pos.holding_duration_minutes, 60.0)

    def test_fifo_scale_in_buys_and_single_sell(self):
        """Test scaling in with 2 BUYs before 1 SELL."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 10, 30, 0)
        t3 = datetime(2026, 8, 1, 11, 0, 0)

        trades = [
            TradeInput(id=1, symbol="TATA", quantity=50, price=100.0, trade_type="BUY", created_at=t1),
            TradeInput(id=2, symbol="TATA", quantity=50, price=110.0, trade_type="BUY", created_at=t2),
            TradeInput(id=3, symbol="TATA", quantity=100, price=120.0, trade_type="SELL", created_at=t3),
        ]

        result = FIFOReconstructor.process_trades(trades)

        self.assertEqual(len(result.closed_positions), 1)
        self.assertEqual(len(result.closed_chunks), 2)
        self.assertEqual(len(result.open_positions), 0)

        pos = result.closed_positions[0]
        self.assertEqual(pos.total_quantity, 100)
        self.assertEqual(pos.weighted_avg_buy_price, 105.0)  # ((50*100) + (50*110)) / 100
        self.assertEqual(pos.weighted_avg_sell_price, 120.0)
        self.assertEqual(pos.realized_pnl, 1500.0)  # (120 - 105) * 100
        self.assertEqual(round(pos.realized_pnl_percent, 2), 14.29)

    def test_fifo_partial_sells_and_remaining_open_lots(self):
        """Test partial SELL leaving an open remaining BUY lot."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 11, 0, 0)

        trades = [
            TradeInput(id=1, symbol="INFY", quantity=100, price=1500.0, trade_type="BUY", created_at=t1),
            TradeInput(id=2, symbol="INFY", quantity=40, price=1600.0, trade_type="SELL", created_at=t2),
        ]

        result = FIFOReconstructor.process_trades(trades)

        self.assertEqual(len(result.closed_positions), 1)
        pos = result.closed_positions[0]
        self.assertEqual(pos.total_quantity, 40)
        self.assertEqual(pos.realized_pnl, 4000.0)  # (1600 - 1500) * 40

        self.assertIn("INFY", result.open_positions)
        open_state = result.open_positions["INFY"]
        self.assertEqual(open_state.total_quantity, 60)
        self.assertEqual(open_state.weighted_avg_buy_price, 1500.0)
        self.assertEqual(open_state.total_invested_amount, 90000.0)

    def test_fifo_unmatched_sell_handling(self):
        """Test short SELL without prior BUY lot."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)

        trades = [
            TradeInput(id=1, symbol="SBIN", quantity=20, price=500.0, trade_type="SELL", created_at=t1),
        ]

        result = FIFOReconstructor.process_trades(trades)

        self.assertEqual(len(result.closed_positions), 0)
        self.assertEqual(len(result.unmatched_sells), 1)
        self.assertEqual(result.unmatched_sells[0]["unmatched_quantity"], 20)

    def test_analytics_metrics_calculation(self):
        """Test AnalyticsEngine performance metrics formulas."""
        t1 = datetime(2026, 8, 1, 10, 0, 0)
        t2 = datetime(2026, 8, 1, 11, 0, 0)
        t3 = datetime(2026, 8, 2, 10, 0, 0)
        t4 = datetime(2026, 8, 2, 12, 0, 0)

        # Position 1: Win +1000, 60 mins duration
        pos1 = ClosedPosition(
            position_id="pos1",
            symbol="RELIANCE",
            total_quantity=10,
            weighted_avg_buy_price=100.0,
            weighted_avg_sell_price=200.0,
            realized_pnl=1000.0,
            realized_pnl_percent=100.0,
            open_timestamp=t1,
            close_timestamp=t2,
            holding_duration_minutes=60.0,
            is_win=True,
            is_loss=False,
            is_breakeven=False,
            chunks=[],
        )

        # Position 2: Loss -500, 120 mins duration
        pos2 = ClosedPosition(
            position_id="pos2",
            symbol="TATA",
            total_quantity=10,
            weighted_avg_buy_price=100.0,
            weighted_avg_sell_price=50.0,
            realized_pnl=-500.0,
            realized_pnl_percent=-50.0,
            open_timestamp=t3,
            close_timestamp=t4,
            holding_duration_minutes=120.0,
            is_win=False,
            is_loss=True,
            is_breakeven=False,
            chunks=[],
        )

        holdings = [
            HoldingItem(symbol="RELIANCE", quantity=10, avg_price=150.0, current_price=200.0, current_value=20000.0),
            HoldingItem(symbol="TATA", quantity=100, avg_price=90.0, current_price=100.0, current_value=10000.0),
        ]

        metrics = AnalyticsEngine.calculate_metrics(
            closed_positions=[pos1, pos2],
            total_raw_trades=4,
            current_holdings=holdings,
            total_portfolio_value=100000.0,
        )

        self.assertEqual(metrics.total_trades_count, 4)
        self.assertEqual(metrics.closed_positions_count, 2)
        self.assertEqual(metrics.winning_positions_count, 1)
        self.assertEqual(metrics.losing_positions_count, 1)
        self.assertEqual(metrics.win_rate_pct, 50.0)

        self.assertEqual(metrics.total_realized_pnl, 500.0)
        self.assertEqual(metrics.total_gross_profit, 1000.0)
        self.assertEqual(metrics.total_gross_loss, 500.0)
        self.assertEqual(metrics.average_profit, 1000.0)
        self.assertEqual(metrics.average_loss, 500.0)

        self.assertEqual(metrics.profit_factor, 2.0)  # 1000 / 500
        self.assertEqual(metrics.risk_reward_ratio, 2.0)  # 1000 / 500

        self.assertEqual(metrics.avg_holding_duration_minutes, 90.0)  # (60 + 120) / 2
        self.assertEqual(metrics.avg_winning_duration_minutes, 60.0)
        self.assertEqual(metrics.avg_losing_duration_minutes, 120.0)
        self.assertEqual(metrics.holding_duration_ratio, 2.0)  # 120 / 60

        # HHI calculation:
        # RELIANCE weight = (20,000 / 100,000) * 100 = 20% -> 20^2 = 400
        # TATA weight = (10,000 / 100,000) * 100 = 10% -> 10^2 = 100
        # Total HHI = 500.0
        self.assertEqual(metrics.portfolio_concentration_hhi, 500.0)
        self.assertEqual(metrics.max_position_sizing_pct, 20.0)
        self.assertEqual(metrics.avg_position_sizing_pct, 15.0)

        # Unrealized PnL: RELIANCE (20,000 - 1,500) = 18,500 + TATA (10,000 - 9,000) = 1,000 -> 19,500.0
        self.assertEqual(metrics.total_unrealized_pnl, 19500.0)

    def test_analytics_metrics_empty_inputs(self):
        """Test AnalyticsEngine with zero trades and empty holdings without error."""
        metrics = AnalyticsEngine.calculate_metrics(
            closed_positions=[],
            total_raw_trades=0,
            current_holdings=[],
            total_portfolio_value=100000.0,
        )

        self.assertEqual(metrics.total_trades_count, 0)
        self.assertEqual(metrics.closed_positions_count, 0)
        self.assertEqual(metrics.win_rate_pct, 0.0)
        self.assertEqual(metrics.profit_factor, 0.0)
        self.assertEqual(metrics.risk_reward_ratio, 0.0)
        self.assertEqual(metrics.portfolio_concentration_hhi, 0.0)


if __name__ == "__main__":
    unittest.main()
