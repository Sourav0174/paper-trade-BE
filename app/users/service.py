from datetime import datetime, timezone
import os
import logging

from sqlalchemy.orm import Session
from app.users.models import SubscriptionEnum, User
from app.mentor.models import MentorReview
from app.trades.models import Holding, Order, Portfolio, Trade
from app.core.security import hash_password, verify_password, create_access_token
from fastapi import HTTPException

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from app.database import get_db
from app.core.security import verify_token
from app.core.security import create_verification_token
from app.core.email import send_password_reset_email, send_verification_email

from google.oauth2 import id_token
from google.auth.transport import requests


logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


def google_login(
    db: Session,
    google_token: str,
):
    try:
        info = id_token.verify_oauth2_token(
            google_token,
            requests.Request(),
            GOOGLE_CLIENT_ID
        )

        google_id = info.get("sub")
        email = info.get("email")
        email_verified = info.get("email_verified")
        name = info.get("name", "Google User")

        if not google_id or not email:
            raise ValueError("Missing google_id or email in token")

        if email_verified is not True and str(email_verified).lower() != "true":
            raise HTTPException(
                status_code=401,
                detail="Google email is not verified"
            )

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid Google token"
        )

    # 1. Look up existing user by google_id
    user = db.query(User).filter(User.google_id == google_id).first()

    if user:
        if user.email != email:
            raise HTTPException(
                status_code=400,
                detail="Google token email is inconsistent with registered user account email"
            )
    else:
        # 2. If no user found by google_id, look up user by email
        user = db.query(User).filter(User.email == email).first()

        if user:
            if user.google_id is not None and user.google_id != google_id:
                raise HTTPException(
                    status_code=400,
                    detail="Account is already linked to a different Google account"
                )

            if user.google_id is None:
                if not user.is_verified:
                    raise HTTPException(
                        status_code=400,
                        detail="Please verify your email address before linking your Google account"
                    )
                user.google_id = google_id
                db.commit()
                db.refresh(user)
        else:
            # 3. Create new Google user
            user = User(
                email=email,
                name=name,
                password=None,
                provider="google",
                google_id=google_id,
                is_verified=True,
                subscription=SubscriptionEnum.FREE
            )

            db.add(user)
            db.commit()
            db.refresh(user)

    token = create_access_token(str(user.id))

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "is_subscribed": user.subscription != SubscriptionEnum.FREE
        }
    }


def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
):
    payload = verify_token(token, expected_type="access")

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


def create_user(db: Session, name: str, gender: str, email: str, password: str):
    logger.info("create_user: starting signup for email=%s", email)

    hashed = hash_password(password)

    user = User(
        name=name,
        gender=gender,
        email=email,
        password=hashed,
        subscription=SubscriptionEnum.FREE,
        is_verified=False,
        password_updated_at=datetime.now(timezone.utc)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    email_str = str(user.email)

    try:
        token = create_verification_token(email_str)
        logger.info("create_user: verification token generated for user_id=%s", user.id)
        send_verification_email(email_str, token)
    except Exception:
        logger.exception(
            "create_user: failed to generate token or send verification email for user_id=%s email=%s",
            user.id, email_str
        )
        raise

    return user


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return None

    if user.password is None:
        raise HTTPException(
            status_code=400,
            detail="Please continue with Google"
        )

    if not verify_password(password, user.password): # type: ignore
        return None

    if user.is_verified is not True:
        raise HTTPException(
            status_code=403,
            detail="Email not verified"
        )

    return user



def login_user(db: Session, email: str, password: str):
    user = authenticate_user(db, email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token(str(user.id))

    

    return token






def forgot_password(db: Session, email: str):
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return {"message": "If this email exists, reset link sent"}

    pwd_at: datetime | None = user.password_updated_at # type: ignore

    token = create_verification_token(
        email,
        token_type="reset",
        password_updated_at=pwd_at or datetime.now(timezone.utc)
    )

    send_password_reset_email(email, token)

    return {"message": "If this email exists, reset link sent"}

def delete_user(db: Session, user_id: int):
    """
    Deletes an authenticated user and all associated records in strict dependency order:
    1. mentor_reviews
    2. orders
    3. trades
    4. holdings
    5. portfolios
    6. users

    Executed within a single database transaction. Rollback on failure.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    try:
        # 1. mentor_reviews
        db.query(MentorReview).filter(MentorReview.user_id == user_id).delete(synchronize_session=False)

        # 2. orders (removes pending and executed orders so scheduler stops processing)
        db.query(Order).filter(Order.user_id == user_id).delete(synchronize_session=False)

        # 3. trades
        db.query(Trade).filter(Trade.user_id == user_id).delete(synchronize_session=False)

        # 4. holdings
        db.query(Holding).filter(Holding.user_id == user_id).delete(synchronize_session=False)

        # 5. portfolios
        db.query(Portfolio).filter(Portfolio.user_id == user_id).delete(synchronize_session=False)

        # 6. users
        db.delete(user)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Error deleting account for user_id=%s: %s", user_id, str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to delete account"
        ) from e

    return {
        "success": True,
        "message": "Account deleted successfully"
    }