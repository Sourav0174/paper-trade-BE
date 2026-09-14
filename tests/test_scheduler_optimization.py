from datetime import datetime, timedelta
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.users.models import User, SubscriptionEnum
from app.trades.models import Portfolio, Order
from app.trades.enums import OrderStatus, OrderType, TradeType
from app.trades.scheduler import (
    EXECUTE_JOB_ID,
    EXPIRE_JOB_ID,
    EXPIRE_SAFETY_JOB_ID,
    execute_pending_orders_job,
    expire_stale_orders_job,
    get_scheduler,
    postgres_advisory_lock,
)


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

    @patch("app.trades.scheduler.SessionLocal")
    def test_expire_stale_orders_job_expires_only_past_orders(self, mock_session_local):
        mock_session_local.return_value = self.db

        now = datetime.utcnow()
        # Order 1: expired 5 minutes ago
        self.order1.expires_at = now - timedelta(minutes=5)
        # Order 2: expires in 2 hours
        self.order2.expires_at = now + timedelta(hours=2)
        # Order 3: no expires_at
        self.order3.expires_at = None
        self.db.commit()

        initial_reserved = self.portfolio.reserved_balance
        expire_stale_orders_job()

        # Order 1 should be EXPIRED and its reservation released
        o1 = self.db.query(Order).get(1)
        self.assertEqual(o1.status, OrderStatus.EXPIRED)
        updated_portfolio = self.db.query(Portfolio).get(1)
        self.assertLess(updated_portfolio.reserved_balance, initial_reserved)

        # Order 2 and 3 should remain PENDING
        o2 = self.db.query(Order).get(2)
        self.assertEqual(o2.status, OrderStatus.PENDING)

        o3 = self.db.query(Order).get(3)
        self.assertEqual(o3.status, OrderStatus.PENDING)

    @patch("app.trades.scheduler.EXPIRY_BATCH_SIZE", 2)
    @patch("app.trades.scheduler.SessionLocal")
    def test_expire_stale_orders_job_batches_properly(self, mock_session_local):
        mock_session_local.return_value = self.db

        now = datetime.utcnow()
        # Mark all 3 orders expired (BATCH_SIZE is 2, so it must loop to process all 3)
        self.order1.expires_at = now - timedelta(minutes=5)
        self.order2.expires_at = now - timedelta(minutes=5)
        self.order3.expires_at = now - timedelta(minutes=5)
        self.db.commit()

        expire_stale_orders_job()

        self.assertEqual(self.db.query(Order).get(1).status, OrderStatus.EXPIRED)
        self.assertEqual(self.db.query(Order).get(2).status, OrderStatus.EXPIRED)
        self.assertEqual(self.db.query(Order).get(3).status, OrderStatus.EXPIRED)

    @patch("app.trades.scheduler.postgres_advisory_lock")
    @patch("app.trades.scheduler.SessionLocal")
    def test_advisory_lock_skips_when_lock_not_acquired(self, mock_session_local, mock_lock):
        mock_session_local.return_value = self.db
        # Simulate another worker holding the advisory lock
        mock_lock.return_value.__enter__.return_value = False

        now = datetime.utcnow()
        self.order1.expires_at = now - timedelta(minutes=5)
        self.db.commit()

        expire_stale_orders_job()

        # Order 1 must NOT be expired because the job skipped execution
        o1 = self.db.query(Order).get(1)
        self.assertEqual(o1.status, OrderStatus.PENDING)

    def test_scheduler_jobs_configuration(self):
        scheduler = get_scheduler()
        job_ids = {job.id for job in scheduler.get_jobs()}

        self.assertIn(EXECUTE_JOB_ID, job_ids)
        self.assertIn(EXPIRE_JOB_ID, job_ids)
        self.assertIn(EXPIRE_SAFETY_JOB_ID, job_ids)

        expire_job = scheduler.get_job(EXPIRE_JOB_ID)
        # Cron trigger: mon-fri at 15:31
        self.assertEqual(str(expire_job.trigger.fields[4]), "mon-fri")
        self.assertEqual(str(expire_job.trigger.fields[5]), "15")
        self.assertEqual(str(expire_job.trigger.fields[6]), "31")

        safety_job = scheduler.get_job(EXPIRE_SAFETY_JOB_ID)
        # Cron trigger: mon-fri at 16:00
        self.assertEqual(str(safety_job.trigger.fields[4]), "mon-fri")
        self.assertEqual(str(safety_job.trigger.fields[5]), "16")
        self.assertEqual(str(safety_job.trigger.fields[6]), "0")


if __name__ == "__main__":
    unittest.main()

