"""
Deterministic Analytics Engine for AI Mentor.

Calculates pure mathematical metrics (Win Rate, Profit Factor, RRR, Drawdown,
Holding Duration, Position Sizing, and Concentration Risk) operating strictly on
reconstructed ClosedPosition objects, primitive values, and HoldingItem contracts.

This module has ZERO dependencies on ORM models, databases, or AI APIs.
"""

from typing import List, Optional
import numpy as np

from app.mentor.schema import (
    AnalyticsMetrics,
    ClosedPosition,
    HoldingItem,
    OpenPositionState,
)


class AnalyticsEngine:
    """
    Deterministic Analytics Engine.

    Takes primitive values and reconstructed closed position schemas to produce
    comprehensive trading statistics and behavioral performance metrics.
    """

    @classmethod
    def calculate_metrics(
        cls,
        closed_positions: List[ClosedPosition],
        total_raw_trades: int = 0,
        current_holdings: Optional[List[HoldingItem]] = None,
        total_portfolio_value: float = 100000.0,
        open_positions: Optional[List[OpenPositionState]] = None,
    ) -> AnalyticsMetrics:
        """
        Calculates all performance and behavioral analytics metrics.

        Args:
            closed_positions: List of reconstructed ClosedPosition objects.
            total_raw_trades: Total count of raw execution trades.
            current_holdings: Current active user holdings for HHI and sizing calculations.
            total_portfolio_value: Total portfolio net worth (cash + current holding value).
            open_positions: List of reconstructed OpenPositionState objects for unrealized P&L.

        Returns:
            AnalyticsMetrics instance populated with computed metrics.
        """
        closed_count = len(closed_positions)

        winning_positions = [p for p in closed_positions if p.is_win]
        losing_positions = [p for p in closed_positions if p.is_loss]
        breakeven_positions = [p for p in closed_positions if p.is_breakeven]

        win_count = len(winning_positions)
        loss_count = len(losing_positions)
        be_count = len(breakeven_positions)

        win_rate = cls._calc_win_rate(win_count, closed_count)

        gross_profit = cls._calc_gross_profit(winning_positions)
        gross_loss = cls._calc_gross_loss(losing_positions)
        total_realized_pnl = round(gross_profit - gross_loss, 2)

        avg_profit = cls._calc_average(gross_profit, win_count)
        avg_loss = cls._calc_average(gross_loss, loss_count)

        profit_factor = cls._calc_profit_factor(gross_profit, gross_loss)
        rrr = cls._calc_risk_reward_ratio(avg_profit, avg_loss)

        max_dd_pct, max_dd_amt = cls._calc_max_drawdown(closed_positions, total_portfolio_value)

        avg_dur, win_dur, loss_dur, dur_ratio = cls._calc_holding_durations(
            closed_positions, winning_positions, losing_positions
        )

        hhi = cls._calc_portfolio_hhi(current_holdings, total_portfolio_value)
        max_sizing, avg_sizing = cls._calc_position_sizing(current_holdings, total_portfolio_value)

        unrealized_pnl = cls._calc_unrealized_pnl(open_positions, current_holdings)

        return AnalyticsMetrics(
            total_trades_count=total_raw_trades,
            closed_positions_count=closed_count,
            winning_positions_count=win_count,
            losing_positions_count=loss_count,
            breakeven_positions_count=be_count,
            win_rate_pct=win_rate,
            total_realized_pnl=total_realized_pnl,
            total_gross_profit=round(gross_profit, 2),
            total_gross_loss=round(gross_loss, 2),
            average_profit=round(avg_profit, 2),
            average_loss=round(avg_loss, 2),
            profit_factor=round(profit_factor, 2),
            risk_reward_ratio=round(rrr, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            max_drawdown_amount=round(max_dd_amt, 2),
            avg_holding_duration_minutes=round(avg_dur, 2),
            avg_winning_duration_minutes=round(win_dur, 2),
            avg_losing_duration_minutes=round(loss_dur, 2),
            holding_duration_ratio=round(dur_ratio, 2),
            portfolio_concentration_hhi=round(hhi, 2),
            max_position_sizing_pct=round(max_sizing, 2),
            avg_position_sizing_pct=round(avg_sizing, 2),
            total_unrealized_pnl=round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
        )

    @staticmethod
    def _calc_win_rate(win_count: int, total_count: int) -> float:
        """Calculates win rate percentage."""
        if total_count == 0:
            return 0.0
        return round((win_count / total_count) * 100, 2)

    @staticmethod
    def _calc_gross_profit(winning_positions: List[ClosedPosition]) -> float:
        """Sum of realized P&L from winning positions."""
        return sum(p.realized_pnl for p in winning_positions)

    @staticmethod
    def _calc_gross_loss(losing_positions: List[ClosedPosition]) -> float:
        """Sum of absolute realized losses from losing positions (returned as positive number)."""
        return sum(abs(p.realized_pnl) for p in losing_positions)

    @staticmethod
    def _calc_average(total_value: float, count: int) -> float:
        """Helper to calculate safe average."""
        if count == 0:
            return 0.0
        return total_value / count

    @staticmethod
    def _calc_profit_factor(gross_profit: float, gross_loss: float) -> float:
        """Calculates Profit Factor (Gross Profit / Gross Loss) with zero-division protection."""
        if gross_loss == 0.0:
            return float(gross_profit) if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def _calc_risk_reward_ratio(avg_profit: float, avg_loss: float) -> float:
        """Calculates Risk-Reward Ratio (Average Profit / Average Loss)."""
        if avg_loss == 0.0:
            return float(avg_profit) if avg_profit > 0 else 0.0
        return avg_profit / avg_loss

    @staticmethod
    def _calc_max_drawdown(
        closed_positions: List[ClosedPosition],
        starting_capital: float = 100000.0
    ) -> tuple[float, float]:
        """
        Calculates Maximum Drawdown percentage and currency amount from cumulative equity curve.

        Returns:
            Tuple of (max_drawdown_pct, max_drawdown_amount)
        """
        if not closed_positions:
            return 0.0, 0.0

        # Sort closed positions by close timestamp ASC
        sorted_positions = sorted(closed_positions, key=lambda p: p.close_timestamp)

        equity_curve = [starting_capital]
        current_equity = starting_capital

        for p in sorted_positions:
            current_equity += p.realized_pnl
            equity_curve.append(current_equity)

        equity_array = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity_array)

        # Drawdown amount per step
        drawdown_amounts = running_max - equity_array
        max_drawdown_amt = float(np.max(drawdown_amounts))

        # Drawdown percentage per step
        drawdown_pcts = np.where(running_max > 0, (drawdown_amounts / running_max) * 100, 0.0)
        max_drawdown_pct = float(np.max(drawdown_pcts))

        return max_drawdown_pct, max_drawdown_amt

    @staticmethod
    def _calc_holding_durations(
        closed_positions: List[ClosedPosition],
        winning_positions: List[ClosedPosition],
        losing_positions: List[ClosedPosition],
    ) -> tuple[float, float, float, float]:
        """
        Calculates holding duration statistics in minutes.

        Returns:
            Tuple of (avg_duration, avg_winning_duration, avg_losing_duration, holding_duration_ratio)
        """
        if not closed_positions:
            return 0.0, 0.0, 0.0, 0.0

        avg_dur = float(np.mean([p.holding_duration_minutes for p in closed_positions]))

        win_dur = float(np.mean([p.holding_duration_minutes for p in winning_positions])) if winning_positions else 0.0
        loss_dur = float(np.mean([p.holding_duration_minutes for p in losing_positions])) if losing_positions else 0.0

        dur_ratio = (loss_dur / win_dur) if win_dur > 0.0 else 0.0

        return avg_dur, win_dur, loss_dur, dur_ratio

    @staticmethod
    def _calc_portfolio_hhi(
        holdings: Optional[List[HoldingItem]],
        total_portfolio_value: float
    ) -> float:
        """
        Calculates Herfindahl-Hirschman Index (HHI) for portfolio concentration.

        HHI = Sum( (Holding Value / Total Portfolio Value * 100)^2 )
        HHI ranges from ~0 to 10,000 (10,000 = 100% single stock).
        """
        if not holdings or total_portfolio_value <= 0:
            return 0.0

        hhi_sum = 0.0
        for item in holdings:
            if item.current_value > 0 and total_portfolio_value > 0:
                weight_pct = (item.current_value / total_portfolio_value) * 100.0
                hhi_sum += weight_pct ** 2

        return hhi_sum

    @staticmethod
    def _calc_position_sizing(
        holdings: Optional[List[HoldingItem]],
        total_portfolio_value: float
    ) -> tuple[float, float]:
        """
        Calculates maximum and average single-position allocation percentages.

        Returns:
            Tuple of (max_position_sizing_pct, avg_position_sizing_pct)
        """
        if not holdings or total_portfolio_value <= 0:
            return 0.0, 0.0

        sizing_pcts = [
            (item.current_value / total_portfolio_value) * 100.0
            for item in holdings
            if item.current_value > 0
        ]

        if not sizing_pcts:
            return 0.0, 0.0

        return float(np.max(sizing_pcts)), float(np.mean(sizing_pcts))

    @staticmethod
    def _calc_unrealized_pnl(
        open_positions: Optional[List[OpenPositionState]],
        holdings: Optional[List[HoldingItem]]
    ) -> Optional[float]:
        """Calculates total unrealized P&L from active open position states and market holdings."""
        if holdings:
            total_unrealized = 0.0
            has_valid_holding = False
            for item in holdings:
                if item.quantity > 0 and item.avg_price > 0:
                    invested = item.quantity * item.avg_price
                    unrealized = item.current_value - invested
                    total_unrealized += unrealized
                    has_valid_holding = True
            if has_valid_holding:
                return round(total_unrealized, 2)

        if open_positions and holdings:
            price_map = {item.symbol: item.current_price for item in holdings}
            total_unrealized = 0.0
            has_valid_pos = False
            for open_pos in open_positions:
                curr_price = price_map.get(open_pos.symbol)
                if curr_price is not None:
                    curr_val = open_pos.total_quantity * curr_price
                    pnl = curr_val - open_pos.total_invested_amount
                    total_unrealized += pnl
                    has_valid_pos = True
            if has_valid_pos:
                return round(total_unrealized, 2)

        return None
