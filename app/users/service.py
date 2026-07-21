from datetime import datetime, timezone
import os
import logging

from sqlalchemy.orm import Session
from app.users.models import SubscriptionEnum, User
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

        google_id = info["sub"]
        email = info["email"]
        name = info.get("name", "Google User")

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid Google token"
        )

    # 👇 CHECK IF USER ALREADY EXISTS
    user = db.query(User).filter(
        User.email == email
    ).first()

    if user and not user.google_id: # type: ignore
        user.google_id = google_id
        user.provider = "google" # type: ignore
        db.commit()
        db.refresh(user)

    # 👇 CREATE ONLY IF NOT FOUND
    if not user:
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

    # 👇 GENERATE YOUR EXISTING JWT
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
    # user_id = verify_token(token, expected_type="access")
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
    password_updated_at=datetime.now(timezone.utc)  # ✅ ADD THIS # type: ignore
)

    db.add(user)
    db.commit()
    db.refresh(user)

   

    email_str = str(user.email)

    try:
       
        token = create_verification_token(email_str)
        # print("CREATED TOKEN:", token)
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

    # Google account
    if user.provider == "google": # type: ignore
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
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    db.delete(user)
    db.commit()

    return {
        "success": True,
        "message": "Account deleted successfully"
    }