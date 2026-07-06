from sqlalchemy.orm import Session

from app.performance.schema import PerformancePeriod
from app.stocks.service import fetch_single_price
from app.trades.models import Holding, Portfolio
import random


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