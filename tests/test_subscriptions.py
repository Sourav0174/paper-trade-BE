"""
Unit tests for Google Play subscription purchase verification in app/subscriptions/service.py.

Tests:
1. Valid purchase with paymentState=1 (payment received) and future expiry -> SUCCESS.
2. Valid purchase with paymentState=2 (free trial) and future expiry -> SUCCESS.
3. Valid production purchase with paymentState absent (None) and future expiry -> SUCCESS.
4. Invalid purchase with paymentState=0 (payment pending) -> REJECTED ("Payment not completed").
5. Invalid purchase with paymentState=3 (pending deferred) -> REJECTED ("Payment not completed").
6. Expired purchase -> REJECTED ("Subscription has expired").
7. Invalid product ID -> REJECTED ("Invalid product ID").
8. Token already linked to another user -> REJECTED ("This purchase is already linked to another account").
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.users.models import User, SubscriptionEnum
from app.subscriptions.service import (
    verify_subscription_purchase,
    restore_subscription_purchase,
)


# In-memory SQLite DB setup for test isolation
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestVerifySubscriptionPurchase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        self.db = TestingSessionLocal()
        self.user = User(
            email="testuser@example.com",
            name="Test User",
            password="hashedpassword123",
            subscription=SubscriptionEnum.FREE,
            is_verified=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.rollback()
        self.db.query(User).delete()
        self.db.commit()
        self.db.close()

    def _get_future_millis(self, hours=24):
        future_dt = datetime.now(timezone.utc) + timedelta(hours=hours)
        return str(int(future_dt.timestamp() * 1000))

    def _get_past_millis(self, hours=24):
        past_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        return str(int(past_dt.timestamp() * 1000))

    @patch("app.subscriptions.service.get_android_publisher")
    def test_verify_success_with_payment_state_1(self, mock_publisher):
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "paymentState": 1,
            "expiryTimeMillis": self._get_future_millis(),
            "acknowledgementState": 1,
            "autoRenewing": True,
        }

        res = verify_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="valid_token_state_1",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["message"], "Subscription verified")
        self.db.refresh(self.user)
        self.assertEqual(self.user.subscription, SubscriptionEnum.PRO)
        self.assertEqual(self.user.purchase_token, "valid_token_state_1")

    @patch("app.subscriptions.service.get_android_publisher")
    def test_verify_success_with_payment_state_2_free_trial(self, mock_publisher):
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "paymentState": 2,
            "expiryTimeMillis": self._get_future_millis(),
            "acknowledgementState": 1,
            "autoRenewing": True,
        }

        res = verify_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="valid_token_state_2",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["message"], "Subscription verified")

    @patch("app.subscriptions.service.get_android_publisher")
    def test_verify_success_with_missing_payment_state(self, mock_publisher):
        """Production Google Play responses omit paymentState for active subscriptions."""
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "expiryTimeMillis": self._get_future_millis(),
            "acknowledgementState": 1,
            "autoRenewing": False,
            "orderId": "GPA.3375-8620-2344-83814",
        }

        res = verify_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="production_token_no_payment_state",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["message"], "Subscription verified")
        self.db.refresh(self.user)
        self.assertEqual(self.user.subscription, SubscriptionEnum.PRO)

    @patch("app.subscriptions.service.get_android_publisher")
    def test_verify_failure_when_payment_state_is_0_pending(self, mock_publisher):
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "paymentState": 0,  # 0 = Payment Pending
            "expiryTimeMillis": self._get_future_millis(),
            "acknowledgementState": 1,
        }

        res = verify_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="token_pending_payment",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["message"], "Payment not completed")

    @patch("app.subscriptions.service.get_android_publisher")
    def test_verify_failure_when_expired(self, mock_publisher):
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "expiryTimeMillis": self._get_past_millis(),
            "acknowledgementState": 1,
        }

        res = verify_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="expired_token",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["message"], "Subscription has expired")

    def test_verify_failure_invalid_product_id(self):
        res = verify_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="invalid.product.sku",
            purchase_token="some_token",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["message"], "Invalid product ID")

    def test_verify_failure_token_linked_to_other(self):
        other_user = User(
            email="other@example.com",
            name="Other User",
            password="hashedpassword123",
            subscription=SubscriptionEnum.PRO,
            purchase_token="duplicate_token",
        )
        self.db.add(other_user)
        self.db.commit()

        res = verify_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="duplicate_token",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["message"], "This purchase is already linked to another account")

    # ==================== RESTORE SUBSCRIPTION TESTS ====================

    @patch("app.subscriptions.service.get_android_publisher")
    def test_restore_success_unlinked_token(self, mock_publisher):
        """Restoring a valid purchase whose previous account was deleted (unlinked in DB)."""
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "expiryTimeMillis": self._get_future_millis(),
            "acknowledgementState": 1,
            "autoRenewing": True,
        }

        res = restore_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="unlinked_active_token",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["message"], "Subscription restored successfully")
        self.db.refresh(self.user)
        self.assertEqual(self.user.subscription, SubscriptionEnum.PRO)
        self.assertEqual(self.user.purchase_token, "unlinked_active_token")

    @patch("app.subscriptions.service.get_android_publisher")
    def test_restore_failure_linked_to_active_other_user(self, mock_publisher):
        """Restoring a token that currently belongs to another active user must be REJECTED."""
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "expiryTimeMillis": self._get_future_millis(),
            "acknowledgementState": 1,
        }

        other_user = User(
            email="activeother@example.com",
            name="Active Other User",
            password="hashedpassword123",
            subscription=SubscriptionEnum.PRO,
            purchase_token="active_token_other_user",
        )
        self.db.add(other_user)
        self.db.commit()

        res = restore_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="active_token_other_user",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["message"], "This purchase is already linked to another account")

    @patch("app.subscriptions.service.get_android_publisher")
    def test_restore_failure_when_expired_on_google_play(self, mock_publisher):
        """Restoring a token that Google Play reports as expired must be REJECTED."""
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "expiryTimeMillis": self._get_past_millis(),
            "acknowledgementState": 1,
        }

        res = restore_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="expired_restore_token",
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["message"], "Subscription has expired")

    @patch("app.subscriptions.service.get_android_publisher")
    def test_restore_success_same_user(self, mock_publisher):
        """Restoring a token that already belongs to the current user refreshes subscription info."""
        mock_service = MagicMock()
        mock_publisher.return_value = mock_service
        mock_service.purchases().subscriptions().get().execute.return_value = {
            "expiryTimeMillis": self._get_future_millis(),
            "acknowledgementState": 1,
            "autoRenewing": True,
        }

        self.user.subscription = SubscriptionEnum.PRO
        self.user.purchase_token = "same_user_token"
        self.db.commit()

        res = restore_subscription_purchase(
            db=self.db,
            user=self.user,
            product_id="papertrade.pro.monthly",
            purchase_token="same_user_token",
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["message"], "Subscription restored successfully")
        self.db.refresh(self.user)
        self.assertEqual(self.user.subscription, SubscriptionEnum.PRO)
        self.assertEqual(self.user.purchase_token, "same_user_token")
