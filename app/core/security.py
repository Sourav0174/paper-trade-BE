from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from fastapi import HTTPException, status
from app.users.models import User
from app.database import SessionLocal
from sqlalchemy.orm import Session
from typing import Optional

load_dotenv()

ACCESS_TOKEN_EXPIRE_MINUTES = 60
VERIFY_TOKEN_EXPIRE_HOURS = 24


def create_access_token(user_id: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "type": "access",
        "exp": expire
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_verification_token(email: str):
    expire = datetime.utcnow() + timedelta(hours=VERIFY_TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": email,
        "type": "verify",
        "exp": expire
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# SECRET_KEY = "supersecretkey"
SECRET_KEY: str = os.environ["SECRET_KEY"]





if SECRET_KEY is None:
    raise ValueError("SECRET_KEY is not set in environment variables")


  # later move to .env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def verify_token(token: str, expected_type: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        token_type = payload.get("type")
        subject = payload.get("sub")

        if token_type != expected_type:
            return None

        if not isinstance(subject, str):
            return None

        return subject

    except JWTError:
        return None



def hash_password(password: str):
    return pwd_context.hash(password[:72])



def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password[:72], hashed_password)






