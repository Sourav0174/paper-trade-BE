"""
Unit tests for Google authentication flow and account linking logic.
"""

import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.users.models import SubscriptionEnum, User
from app.users.service import authenticate_user
from app.core.security import hash_password

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestGoogleAuthenticationFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        self.db = TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.rollback()
        self.db.query(User).delete()
        self.db.commit()
        self.db.close()

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_new_google_user(self, mock_verify):
        """Test signing in with a new Google account creates a user with provider='google' and password=None."""
        mock_verify.return_value = {
            "sub": "google_12345",
            "email": "newgoogle@example.com",
            "email_verified": True,
            "name": "New Google User"
        }

        res = self.client.post("/users/google-login", json={"id_token": "valid_token"})

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["email"], "newgoogle@example.com")

        # Verify DB state
        user = self.db.query(User).filter(User.email == "newgoogle@example.com").first()
        self.assertIsNotNone(user)
        self.assertEqual(user.google_id, "google_12345")
        self.assertEqual(user.provider, "google")
        self.assertIsNone(user.password)
        self.assertTrue(user.is_verified)

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_existing_google_user(self, mock_verify):
        """Test existing Google user signing in again authenticates successfully."""
        existing = User(
            email="existinggoogle@example.com",
            name="Existing Google",
            password=None,
            provider="google",
            google_id="google_12345",
            is_verified=True,
            subscription=SubscriptionEnum.FREE
        )
        self.db.add(existing)
        self.db.commit()

        mock_verify.return_value = {
            "sub": "google_12345",
            "email": "existinggoogle@example.com",
            "email_verified": True,
            "name": "Existing Google"
        }

        res = self.client.post("/users/google-login", json={"id_token": "valid_token"})

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["user"]["id"], existing.id)

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_verified_email_password_user_linking_google(self, mock_verify):
        """Test a verified email/password user linking Google sets google_id but preserves provider='email'."""
        user = User(
            email="verified@example.com",
            name="Verified Email User",
            password=hash_password("Password123!"),
            provider="email",
            google_id=None,
            is_verified=True,
            subscription=SubscriptionEnum.FREE
        )
        self.db.add(user)
        self.db.commit()

        mock_verify.return_value = {
            "sub": "google_67890",
            "email": "verified@example.com",
            "email_verified": True,
            "name": "Verified Email User"
        }

        res = self.client.post("/users/google-login", json={"id_token": "valid_token"})

        self.assertEqual(res.status_code, 200)

        # Check DB state
        self.db.refresh(user)
        self.assertEqual(user.google_id, "google_67890")
        self.assertEqual(user.provider, "email")  # Provider preserved!

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_verified_linked_user_can_still_password_login(self, mock_verify):
        """Test that after linking Google, the user can still log in via email and password."""
        raw_password = "Password123!"
        user = User(
            email="linked@example.com",
            name="Linked User",
            password=hash_password(raw_password),
            provider="email",
            google_id="google_555",
            is_verified=True,
            subscription=SubscriptionEnum.FREE
        )
        self.db.add(user)
        self.db.commit()

        res = self.client.post("/users/login", json={"email": "linked@example.com", "password": raw_password})
        self.assertEqual(res.status_code, 200)
        self.assertIn("access_token", res.json())

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_unverified_email_password_user_cannot_automatically_link_google(self, mock_verify):
        """Test unverified email/password user cannot automatically link Google account."""
        user = User(
            email="unverified@example.com",
            name="Unverified User",
            password=hash_password("Password123!"),
            provider="email",
            google_id=None,
            is_verified=False,
            subscription=SubscriptionEnum.FREE
        )
        self.db.add(user)
        self.db.commit()

        mock_verify.return_value = {
            "sub": "google_99999",
            "email": "unverified@example.com",
            "email_verified": True,
            "name": "Unverified User"
        }

        res = self.client.post("/users/google-login", json={"id_token": "valid_token"})

        self.assertEqual(res.status_code, 400)
        self.assertIn("verify your email address", res.json().get("detail", ""))

        # Ensure google_id was NOT linked
        self.db.refresh(user)
        self.assertIsNone(user.google_id)

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_mismatched_google_id_is_rejected(self, mock_verify):
        """Test if user has google_id='google_111' but token has google_id='google_222' for same email, reject."""
        user = User(
            email="mismatch@example.com",
            name="Mismatch User",
            password=None,
            provider="google",
            google_id="google_111",
            is_verified=True,
            subscription=SubscriptionEnum.FREE
        )
        self.db.add(user)
        self.db.commit()

        mock_verify.return_value = {
            "sub": "google_222",
            "email": "mismatch@example.com",
            "email_verified": True,
            "name": "Mismatch User"
        }

        res = self.client.post("/users/google-login", json={"id_token": "valid_token"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("different Google account", res.json().get("detail", ""))

    @patch("google.oauth2.id_token.verify_oauth2_token")
    def test_google_token_with_unverified_email_is_rejected(self, mock_verify):
        """Test Google ID token with email_verified=False is rejected with HTTP 401."""
        mock_verify.return_value = {
            "sub": "google_333",
            "email": "unverifiedgoogle@example.com",
            "email_verified": False,
            "name": "Unverified Google Token"
        }

        res = self.client.post("/users/google-login", json={"id_token": "valid_token"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("not verified", res.json().get("detail", ""))

    def test_google_only_user_cannot_password_login(self):
        """Test user with password=None cannot log in via email/password endpoint."""
        user = User(
            email="googleonly@example.com",
            name="Google Only",
            password=None,
            provider="google",
            google_id="google_444",
            is_verified=True,
            subscription=SubscriptionEnum.FREE
        )
        self.db.add(user)
        self.db.commit()

        res = self.client.post("/users/login", json={"email": "googleonly@example.com", "password": "AnyPassword123!"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Please continue with Google", res.json().get("detail", ""))


if __name__ == "__main__":
    unittest.main()
