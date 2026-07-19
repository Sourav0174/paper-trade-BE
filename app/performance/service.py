import random
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.performance.schema import PerformancePeriod, PerformancePoint
from app.stocks.service import (
    fetch_single_price,
    get_cached_historical_prices,
)
from app.trades.models import Holding, Portfolio, Trade


HISTORY_RANGES: Dict[PerformancePeriod, tuple[str, str]] = {
    PerformancePeriod.TODAY: ("1d", "1h"),
    PerformancePeriod.WEEK: ("5d", "1d"),
    PerformancePeriod.MONTH: ("1mo", "1wk"),
}

STARTING_BALANCE = 100000.0


class PerformanceService:

    async def get_portfolio_performance(
        self,
        db: Session,
        user_id: int,
        period: PerformancePeriod,
    ):

        portfolio = (
            db.query(Portfolio)
            .filter(Portfolio.user_id == user_id)
            .first()
        )

        if not portfolio:
            return {
                "period": period,
                "currentValue": 100000.0,
                "pnl": 0.0,
                "pnlPercent": 0.0,
                "isPositive": True,
                "history": [],
            }

        holdings = (
            db.query(Holding)
            .filter(
                Holding.user_id == user_id,
                Holding.quantity > 0,
            )
            .all()
        )

        current_value = 0.0

        for holding in holdings:

            live_price = fetch_single_price(
                holding.symbol,
            )

            if live_price is None:
                live_price = holding.avg_price

            current_value += (
                live_price * holding.quantity
            )

        net_worth = (
            portfolio.available_balance
            + current_value
        )

        pnl = (
            portfolio.realized_pnl
            + (
                current_value
                - portfolio.invested_amount
            )
        )

        if portfolio.total_balance == 0:
            pnl_percent = 0
        else:
            pnl_percent = (
                pnl / portfolio.total_balance
            ) * 100

        history = await self._get_real_history(
            db,
            user_id,
            period,
        )

        if not history:
            history = self._generate_history(
                period,
                net_worth,
            )

        return {
            "period": period,
            "currentValue": round(net_worth, 2),
            "pnl": round(pnl, 2),
            "pnlPercent": round(pnl_percent, 2),
            "isPositive": pnl >= 0,
            "history": history,
        }

    async def _get_user_trades(
        self,
        db: Session,
        user_id: int,
    ) -> List[Trade]:

        return (
            db.query(Trade)
            .filter(Trade.user_id == user_id)
            .order_by(Trade.created_at.asc())
            .all()
        )

    @staticmethod
    def _get_portfolio_state_at_timestamp(
        trades: List[Trade],
        timestamp: datetime,
        starting_balance: float = STARTING_BALANCE,
    ) -> Dict[str, Any]:

        cash = starting_balance
        holdings: Dict[str, Dict[str, Any]] = {}

        for trade in trades:

            # Trades are sorted ASC, so the first one past the
            # cutoff means every remaining trade is too.
            if trade.created_at > timestamp:
                break

            symbol = trade.symbol
            position = holdings.get(symbol)
            trade_value = trade.price * trade.quantity

            if trade.trade_type.upper() == "BUY":

                cash -= trade_value

                if position is None:
                    holdings[symbol] = {
                        "quantity": trade.quantity,
                        "avg_price": trade.price,
                    }
                    continue

                total_quantity = (
                    position["quantity"]
                    + trade.quantity
                )

                position["avg_price"] = (
                    position["avg_price"] * position["quantity"]
                    + trade_value
                ) / total_quantity

                position["quantity"] = total_quantity

            else:

                if position is None:
                    continue

                cash += trade_value

                position["quantity"] -= trade.quantity

                if position["quantity"] <= 0:
                    del holdings[symbol]

        return {
            "cash": cash,
            "holdings": holdings,
        }

    @staticmethod
    def _fetch_price_history(
        symbols: List[str],
        period: PerformancePeriod,
    ) -> Dict[str, pd.DataFrame]:

        range_period, interval = HISTORY_RANGES[period]

        return {
            symbol: get_cached_historical_prices(
                symbol,
                range_period,
                interval,
            )
            for symbol in symbols
        }

    @staticmethod
    def _close_at_or_before(
        closes: pd.Series,
        timestamp: pd.Timestamp,
    ) -> float:

        position = closes.index.searchsorted(
            timestamp,
            side="right",
        ) - 1

        if position < 0:
            return float(closes.iloc[0])

        return float(closes.iloc[position])

    @staticmethod
    def _to_naive_utc(timestamp: pd.Timestamp) -> datetime:

        if timestamp.tzinfo is None:
            return timestamp.to_pydatetime()

        return (
            timestamp
            .tz_convert("UTC")
            .tz_localize(None)
            .to_pydatetime()
        )

    @staticmethod
    def _format_label(
        timestamp: pd.Timestamp,
        period: PerformancePeriod,
        index: int,
        is_last: bool,
    ) -> str:

        if period == PerformancePeriod.TODAY:
            hour = timestamp.hour % 12 or 12
            suffix = "AM" if timestamp.hour < 12 else "PM"
            return f"{hour}{suffix}"

        if is_last:
            return "Today"

        if period == PerformancePeriod.WEEK:
            return timestamp.strftime("%a")

        return f"W{index + 1}"

    async def _get_real_history(
        self,
        db: Session,
        user_id: int,
        period: PerformancePeriod,
    ) -> List[PerformancePoint]:

        trades = await self._get_user_trades(db, user_id)

        if not trades:
            return []

        symbols = list(
            dict.fromkeys(
                trade.symbol
                for trade in trades
            )
        )

        price_history = self._fetch_price_history(
            symbols,
            period,
        )

        close_series: Dict[str, pd.Series] = {}

        for symbol in symbols:

            frame = price_history.get(symbol)

            if frame is None or frame.empty or "Close" not in frame:
                continue

            closes = frame["Close"].dropna()

            if not closes.empty:
                close_series[symbol] = closes

        if not close_series:
            return []

        timeline = max(close_series.values(), key=len,).index

        history: List[PerformancePoint] = []
        last_index = len(timeline) - 1

        for index, timestamp in enumerate(timeline):

            cutoff = self._to_naive_utc(timestamp)

            state = self._get_portfolio_state_at_timestamp(
                trades,
                cutoff,
            )

            value = state["cash"]

            for symbol, position in state["holdings"].items():

                closes = close_series.get(symbol)

                if closes is None:
                    continue

                value += (
                    self._close_at_or_before(closes, timestamp)
                    * position["quantity"]
                )

            history.append(
                PerformancePoint(
                    label=self._format_label(
                        timestamp,
                        period,
                        index,
                        index == last_index,
                    ),
                    value=round(value, 2),
                )
            )

        return history

    def _generate_history(
            self,
            period: PerformancePeriod,
            current_value: float,
        ):

            if period == PerformancePeriod.TODAY:
                labels = [
                    "9AM",
                    "10AM",
                    "11AM",
                    "12PM",
                    "1PM",
                    "2PM",
                    "3PM",
                ]
                volatility = 0.003       # 0.3%

            elif period == PerformancePeriod.WEEK:
                labels = [
                    "Mon",
                    "Tue",
                    "Wed",
                    "Thu",
                    "Fri",
                    "Sat",
                    "Today",
                ]
                volatility = 0.012       # 1.2%

            else:
                labels = [
                    "W1",
                    "W2",
                    "W3",
                    "W4",
                    "Today",
                ]
                volatility = 0.03        # 3%

            count = len(labels)

            history = []

            start_value = current_value * (
                1 - random.uniform(0.01, volatility)
            )

            values = [start_value]

            for _ in range(count - 2):

                previous = values[-1]

                movement = random.uniform(
                    -volatility,
                    volatility,
                )

                next_value = previous * (1 + movement)

                values.append(next_value)

            values.append(current_value)

            history = [
                {
                    "label": label,
                    "value": round(value, 2),
                }
                for label, value in zip(labels, values)
            ]

            return history


performance_service = PerformanceService()