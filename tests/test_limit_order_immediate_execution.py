import unittest
from unittest.mock import patch
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.users.models import User, SubscriptionEnum
from app.trades.models import Portfolio, Holding, Order, Trade
from app.trades.enums import OrderStatus, OrderType, TradeType
from app.trades.schema import OrderCreate
from app.trades.order_service import OrderService
from app.trades.scheduler import execute_pending_orders_job


class TestLimitOrderImmediateExecution(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        # Create user
        self.user = User(
            id=1,
            email="test@example.com",
            password="hash",
            name="Test User",
            subscription=SubscriptionEnum.FREE,
        )
        self.db.add(self.user)

        # Create portfolio with 100,000 balance
        self.portfolio = Portfolio(
            id=1,
            user_id=1,
            available_balance=100000.0,
            reserved_balance=0.0,
            invested_amount=0.0,
            realized_pnl=0.0,
        )
        self.db.add(self.portfolio)
        self.db.commit()

        self.order_service = OrderService()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    @patch("app.trades.order_service.get_market_status", return_value="OPEN")
    @patch("app.trades.order_service.fetch_single_price", return_value=2400.0)
    def test_marketable_buy_limit_executes_immediately(self, mock_price, mock_status):
        """
        Market Price = 2400.0
        Limit Price = 2450.0 (BUY)
        Expected: Executes immediately at 2400.0
        """
        data = OrderCreate(
            symbol="RELIANCE",
            quantity=10,
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            limit_price=2450.0,
        )

        order = self.order_service.create_order(self.db, self.user.id, data)

        self.assertEqual(order.status, OrderStatus.EXECUTED)
        self.assertEqual(order.executed_price, 2400.0)
        self.assertIsNotNone(order.executed_at)

        # Verify balance & holdings
        self.db.refresh(self.portfolio)
        # Total cost = 10 * 2400 = 24000
        self.assertEqual(self.portfolio.available_balance, 76000.0)
        self.assertEqual(self.portfolio.reserved_balance, 0.0)
        self.assertEqual(self.portfolio.invested_amount, 24000.0)

        holding = self.db.query(Holding).filter(Holding.user_id == 1, Holding.symbol == "RELIANCE").first()
        self.assertIsNotNone(holding)
        self.assertEqual(holding.quantity, 10)
        self.assertEqual(holding.avg_price, 2400.0)

    @patch("app.trades.order_service.get_market_status", return_value="OPEN")
    @patch("app.trades.order_service.fetch_single_price", return_value=2400.0)
    def test_non_marketable_buy_limit_remains_pending(self, mock_price, mock_status):
        """
        Market Price = 2400.0
        Limit Price = 2350.0 (BUY)
        Expected: Remains PENDING, reserves 10 * 2350 = 23500
        """
        data = OrderCreate(
            symbol="RELIANCE",
            quantity=10,
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            limit_price=2350.0,
        )

        order = self.order_service.create_order(self.db, self.user.id, data)

        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertIsNone(order.executed_price)
        self.assertEqual(order.reserved_amount, 23500.0)

        self.db.refresh(self.portfolio)
        self.assertEqual(self.portfolio.available_balance, 76500.0)
        self.assertEqual(self.portfolio.reserved_balance, 23500.0)

    @patch("app.trades.order_service.get_market_status", return_value="OPEN")
    @patch("app.trades.order_service.fetch_single_price", return_value=2400.0)
    def test_marketable_sell_limit_executes_immediately(self, mock_price, mock_status):
        """
        Holding = 100 shares @ avg 2000.0
        Market Price = 2400.0
        Limit Price = 2350.0 (SELL)
        Expected: Executes immediately at 2400.0
        """
        holding = Holding(
            user_id=1,
            symbol="RELIANCE",
            quantity=100,
            avg_price=2000.0,
            invested_amount=200000.0,
            reserved_quantity=0,
            realized_pnl=0.0,
        )
        self.db.add(holding)
        self.db.commit()

        data = OrderCreate(
            symbol="RELIANCE",
            quantity=40,
            trade_type=TradeType.SELL,
            order_type=OrderType.LIMIT,
            limit_price=2350.0,
        )

        order = self.order_service.create_order(self.db, self.user.id, data)

        self.assertEqual(order.status, OrderStatus.EXECUTED)
        self.assertEqual(order.executed_price, 2400.0)

        self.db.refresh(holding)
        self.assertEqual(holding.quantity, 60)
        self.assertEqual(holding.reserved_quantity, 0)

        self.db.refresh(self.portfolio)
        # 100,000 + (40 * 2400) = 196,000
        self.assertEqual(self.portfolio.available_balance, 196000.0)

    @patch("app.trades.order_service.get_market_status", return_value="OPEN")
    @patch("app.trades.order_service.fetch_single_price", return_value=2400.0)
    def test_non_marketable_sell_limit_remains_pending_and_cancellable(self, mock_price, mock_status):
        """
        Holding = 100 shares
        Market Price = 2400.0
        Limit Price = 2450.0 (SELL)
        Expected: Remains PENDING, reserves 40 shares. Cancellation releases reserved shares.
        """
        holding = Holding(
            user_id=1,
            symbol="RELIANCE",
            quantity=100,
            avg_price=2000.0,
            invested_amount=200000.0,
            reserved_quantity=0,
            realized_pnl=0.0,
        )
        self.db.add(holding)
        self.db.commit()

        data = OrderCreate(
            symbol="RELIANCE",
            quantity=40,
            trade_type=TradeType.SELL,
            order_type=OrderType.LIMIT,
            limit_price=2450.0,
        )

        order = self.order_service.create_order(self.db, self.user.id, data)

        self.assertEqual(order.status, OrderStatus.PENDING)

        self.db.refresh(holding)
        self.assertEqual(holding.reserved_quantity, 40)

        # Cancel order
        cancelled = self.order_service.cancel_order(self.db, self.user.id, order.id)
        self.assertEqual(cancelled.status, OrderStatus.CANCELLED)

        self.db.refresh(holding)
        self.assertEqual(holding.reserved_quantity, 0)


if __name__ == "__main__":
    unittest.main()
