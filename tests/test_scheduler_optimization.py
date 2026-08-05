import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.users.models import User, SubscriptionEnum
from app.trades.models import Portfolio, Order
from app.trades.enums import OrderStatus, OrderType, TradeType
from app.trades.scheduler import execute_pending_orders_job


class TestSchedulerOptimization(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        self.user = User(
            id=1,
            email="test@example.com",
            password="hash",
            name="Test User",
            subscription=SubscriptionEnum.FREE,
        )
        self.db.add(self.user)

        self.portfolio = Portfolio(
            id=1,
            user_id=1,
            available_balance=100000.0,
            reserved_balance=24500.0,
            invested_amount=0.0,
            realized_pnl=0.0,
        )
        self.db.add(self.portfolio)

        # Create 3 pending orders across 2 unique symbols
        self.order1 = Order(
            id=1,
            user_id=1,
            symbol="RELIANCE",
            quantity=10,
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            limit_price=2450.0,
            reserved_amount=24500.0,
            status=OrderStatus.PENDING,
        )
        self.order2 = Order(
            id=2,
            user_id=1,
            symbol="RELIANCE",
            quantity=5,
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            limit_price=2420.0,
            reserved_amount=12100.0,
            status=OrderStatus.PENDING,
        )
        self.order3 = Order(
            id=3,
            user_id=1,
            symbol="TCS",
            quantity=2,
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            limit_price=3500.0,
            reserved_amount=7000.0,
            status=OrderStatus.PENDING,
        )
        self.db.add_all([self.order1, self.order2, self.order3])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    @patch("app.trades.scheduler.SessionLocal")
    @patch("app.trades.scheduler.get_market_status", return_value="OPEN")
    @patch("app.trades.scheduler.fetch_multiple_prices")
    @patch("app.trades.scheduler.fetch_single_price")
    def test_scheduler_batch_fetches_prices_once_per_symbol(
        self, mock_single_fetch, mock_batch_fetch, mock_status, mock_session_local
    ):
        mock_session_local.return_value = self.db

        # Mock batch response: RELIANCE = 2400.0 (executes order1 & order2), TCS = 3600.0 (does not execute order3)
        mock_batch_fetch.return_value = {
            "RELIANCE": (2400.0, 0.0, 0.0),
            "TCS": (3600.0, 0.0, 0.0),
        }

        execute_pending_orders_job()

        # Batch fetch should be called ONCE with the set/list of unique symbols
        mock_batch_fetch.assert_called_once()
        called_symbols = set(mock_batch_fetch.call_args[0][0])
        self.assertEqual(called_symbols, {"RELIANCE", "TCS"})

        # Single fetch should NOT be called since all prices were resolved in batch
        mock_single_fetch.assert_not_called()

        # Order 1 (BUY @ 2450, live 2400) -> EXECUTED
        o1 = self.db.query(Order).get(1)
        self.assertEqual(o1.status, OrderStatus.EXECUTED)
        self.assertEqual(o1.executed_price, 2400.0)

        # Order 2 (BUY @ 2420, live 2400) -> EXECUTED
        o2 = self.db.query(Order).get(2)
        self.assertEqual(o2.status, OrderStatus.EXECUTED)
        self.assertEqual(o2.executed_price, 2400.0)

        # Order 3 (BUY @ 3500, live 3600) -> PENDING
        o3 = self.db.query(Order).get(3)
        self.assertEqual(o3.status, OrderStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
