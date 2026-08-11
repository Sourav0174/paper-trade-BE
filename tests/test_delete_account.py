"""
Unit tests for DELETE /users/delete-account API endpoint and user deletion service logic.

Tests:
1. User with no trading data is deleted successfully.
2. User with portfolio, holdings, and trades is deleted cleanly.
3. User with pending orders is deleted (removing pending orders so background scheduler won't touch them).
4. User with mentor reviews is deleted cleanly (handling Foreign Key constraint without 500 error).
5. Verification that all user-owned records (mentor_reviews, orders, trades, holdings, portfolios, users) are completely gone after deletion.
6. Verification that another user's records (User, Portfolio, Holding, Trade, Order, MentorReview) remain untouched.
"""

import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.users.models import SubscriptionEnum, User
from app.trades.models import Holding, Order, Portfolio, Trade
from app.trades.enums import OrderStatus, OrderType, TradeType
from app.mentor.models import MentorReview
from app.users.service import get_current_user


# Setup shared in-memory SQLite database for test isolation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestDeleteAccountEndpoint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Create all tables in the shared in-memory test database."""
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        """Drop all tables after tests complete."""
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        """Set up a fresh DB session and TestClient for each test."""
        self.db = TestingSessionLocal()
        
        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        """Clean up session, dependency overrides, and data after each test."""
        app.dependency_overrides.clear()
        self.db.rollback()
        # Clean all rows from all tables
        self.db.query(MentorReview).delete()
        self.db.query(Order).delete()
        self.db.query(Trade).delete()
        self.db.query(Holding).delete()
        self.db.query(Portfolio).delete()
        self.db.query(User).delete()
        self.db.commit()
        self.db.close()

    def _create_user(self, email="testuser@example.com", name="Test User"):
        user = User(
            email=email,
            name=name,
            password="hashedpassword123",
            subscription=SubscriptionEnum.FREE,
            is_verified=True
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def _set_auth_user(self, user_id: int):
        def _get_current_user_override():
            return self.db.query(User).filter(User.id == user_id).first()
        app.dependency_overrides[get_current_user] = _get_current_user_override

    def test_delete_account_user_with_no_trading_data(self):
        """Test deleting a user who has no portfolio, trades, or orders."""
        user = self._create_user(email="empty@example.com", name="Empty User")
        user_id = user.id

        self._set_auth_user(user_id)

        res = self.client.delete("/users/delete-account")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("message"), "Account deleted successfully")

        # Verify user record is gone
        deleted_user = self.db.query(User).filter(User.id == user_id).first()
        self.assertIsNone(deleted_user)

    def test_delete_account_user_with_portfolio_holdings_trades(self):
        """Test deleting a user who has portfolio, holdings, and trade history."""
        user = self._create_user(email="trader@example.com", name="Trader User")
        user_id = user.id

        # Add portfolio, holding, and trade
        portfolio = Portfolio(user_id=user_id, total_balance=100000.0, available_balance=80000.0, invested_amount=20000.0)
        holding = Holding(user_id=user_id, symbol="AAPL", quantity=10, avg_price=150.0, invested_amount=1500.0)
        trade = Trade(user_id=user_id, symbol="AAPL", quantity=10, price=150.0, trade_type="BUY")
        self.db.add_all([portfolio, holding, trade])
        self.db.commit()

        self._set_auth_user(user_id)

        res = self.client.delete("/users/delete-account")
        self.assertEqual(res.status_code, 200)

        # Verify all user-owned records are gone
        self.assertIsNone(self.db.query(User).filter(User.id == user_id).first())
        self.assertIsNone(self.db.query(Portfolio).filter(Portfolio.user_id == user_id).first())
        self.assertEqual(self.db.query(Holding).filter(Holding.user_id == user_id).all(), [])
        self.assertEqual(self.db.query(Trade).filter(Trade.user_id == user_id).all(), [])

    def test_delete_account_user_with_pending_orders(self):
        """Test deleting a user with pending limit/market orders removes orders so background scheduler stops processing them."""
        user = self._create_user(email="orders@example.com", name="Orders User")
        user_id = user.id

        order = Order(
            user_id=user_id,
            symbol="GOOGL",
            quantity=5,
            trade_type=TradeType.BUY,
            order_type=OrderType.LIMIT,
            limit_price=140.0,
            status=OrderStatus.PENDING,
            reserved_amount=700.0
        )
        self.db.add(order)
        self.db.commit()

        self._set_auth_user(user_id)

        res = self.client.delete("/users/delete-account")
        self.assertEqual(res.status_code, 200)

        # Verify pending order and user are deleted
        self.assertIsNone(self.db.query(User).filter(User.id == user_id).first())
        self.assertEqual(self.db.query(Order).filter(Order.user_id == user_id).all(), [])

    def test_delete_account_user_with_mentor_reviews(self):
        """Test deleting a user with mentor reviews (which have foreign key to users.id) without FK constraint error."""
        user = self._create_user(email="mentor@example.com", name="Mentor User")
        user_id = user.id

        mentor_review = MentorReview(
            user_id=user_id,
            review_type="DAILY",
            health_score=88.5,
            trading_grade="DISCIPLINED",
            summary_json={"score": 88.5},
            response_json={"message": "Good trading"},
            trade_count=3,
            stale=False
        )
        self.db.add(mentor_review)
        self.db.commit()

        self._set_auth_user(user_id)

        res = self.client.delete("/users/delete-account")
        self.assertEqual(res.status_code, 200)

        # Verify mentor review and user are deleted
        self.assertIsNone(self.db.query(User).filter(User.id == user_id).first())
        self.assertEqual(self.db.query(MentorReview).filter(MentorReview.user_id == user_id).all(), [])

    def test_verify_user_and_all_associated_records_are_gone(self):
        """Comprehensive test verifying deletion across all 6 tables for the target user."""
        user = self._create_user(email="full@example.com", name="Full User")
        user_id = user.id

        portfolio = Portfolio(user_id=user_id, total_balance=50000.0, available_balance=50000.0)
        holding = Holding(user_id=user_id, symbol="MSFT", quantity=5, avg_price=300.0)
        trade = Trade(user_id=user_id, symbol="MSFT", quantity=5, price=300.0, trade_type="BUY")
        order = Order(user_id=user_id, symbol="MSFT", quantity=5, trade_type=TradeType.BUY, order_type=OrderType.MARKET, status=OrderStatus.EXECUTED)
        review = MentorReview(user_id=user_id, review_type="DAILY", health_score=90.0, trading_grade="A", summary_json={}, response_json={})

        self.db.add_all([portfolio, holding, trade, order, review])
        self.db.commit()

        self._set_auth_user(user_id)

        res = self.client.delete("/users/delete-account")
        self.assertEqual(res.status_code, 200)

        # Assert zero records remain across all tables for user_id
        self.assertIsNone(self.db.query(User).filter(User.id == user_id).first())
        self.assertIsNone(self.db.query(Portfolio).filter(Portfolio.user_id == user_id).first())
        self.assertEqual(self.db.query(Holding).filter(Holding.user_id == user_id).all(), [])
        self.assertEqual(self.db.query(Trade).filter(Trade.user_id == user_id).all(), [])
        self.assertEqual(self.db.query(Order).filter(Order.user_id == user_id).all(), [])
        self.assertEqual(self.db.query(MentorReview).filter(MentorReview.user_id == user_id).all(), [])

    def test_verify_another_users_records_are_untouched(self):
        """Verify deleting User A does NOT affect User B or any of User B's associated records."""
        user_a = self._create_user(email="usera@example.com", name="User A")
        user_b = self._create_user(email="userb@example.com", name="User B")

        # Create records for User A
        portfolio_a = Portfolio(user_id=user_a.id, total_balance=10000.0)
        holding_a = Holding(user_id=user_a.id, symbol="TSLA", quantity=2, avg_price=200.0)
        trade_a = Trade(user_id=user_a.id, symbol="TSLA", quantity=2, price=200.0, trade_type="BUY")
        order_a = Order(user_id=user_a.id, symbol="TSLA", quantity=2, trade_type=TradeType.BUY, order_type=OrderType.MARKET, status=OrderStatus.EXECUTED)
        review_a = MentorReview(user_id=user_a.id, review_type="DAILY", health_score=70.0, trading_grade="C", summary_json={}, response_json={})
        self.db.add_all([portfolio_a, holding_a, trade_a, order_a, review_a])

        # Create records for User B
        portfolio_b = Portfolio(user_id=user_b.id, total_balance=25000.0)
        holding_b = Holding(user_id=user_b.id, symbol="NVDA", quantity=10, avg_price=120.0)
        trade_b = Trade(user_id=user_b.id, symbol="NVDA", quantity=10, price=120.0, trade_type="BUY")
        order_b = Order(user_id=user_b.id, symbol="NVDA", quantity=10, trade_type=TradeType.BUY, order_type=OrderType.LIMIT, limit_price=115.0, status=OrderStatus.PENDING)
        review_b = MentorReview(user_id=user_b.id, review_type="DAILY", health_score=95.0, trading_grade="A", summary_json={}, response_json={})
        self.db.add_all([portfolio_b, holding_b, trade_b, order_b, review_b])

        self.db.commit()

        # Delete User A
        self._set_auth_user(user_a.id)

        res = self.client.delete("/users/delete-account")
        self.assertEqual(res.status_code, 200)

        # Verify User A's records are gone
        self.assertIsNone(self.db.query(User).filter(User.id == user_a.id).first())
        self.assertIsNone(self.db.query(Portfolio).filter(Portfolio.user_id == user_a.id).first())
        self.assertEqual(self.db.query(Holding).filter(Holding.user_id == user_a.id).all(), [])
        self.assertEqual(self.db.query(Trade).filter(Trade.user_id == user_a.id).all(), [])
        self.assertEqual(self.db.query(Order).filter(Order.user_id == user_a.id).all(), [])
        self.assertEqual(self.db.query(MentorReview).filter(MentorReview.user_id == user_a.id).all(), [])

        # Verify User B's records are completely UNTOUCHED
        self.assertIsNotNone(self.db.query(User).filter(User.id == user_b.id).first())
        self.assertIsNotNone(self.db.query(Portfolio).filter(Portfolio.user_id == user_b.id).first())
        self.assertEqual(len(self.db.query(Holding).filter(Holding.user_id == user_b.id).all()), 1)
        self.assertEqual(len(self.db.query(Trade).filter(Trade.user_id == user_b.id).all()), 1)
        self.assertEqual(len(self.db.query(Order).filter(Order.user_id == user_b.id).all()), 1)
        self.assertEqual(len(self.db.query(MentorReview).filter(MentorReview.user_id == user_b.id).all()), 1)


if __name__ == "__main__":
    unittest.main()
