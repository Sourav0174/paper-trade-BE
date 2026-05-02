from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
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
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": user_id,
        "type": "access",
        "exp": expire
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)




def create_verification_token(
    email: str,
    token_type: str = "verify",
    password_updated_at: datetime | None = None
):
    if token_type == "verify":
        expire = datetime.now(timezone.utc) + timedelta(hours=24)
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=10)

    payload = {
        "sub": email,
        "type": token_type,
        "exp": expire,
        # ✅ FIX: store timestamp instead of string
        "pwd_at": int(password_updated_at.timestamp()) if password_updated_at else 0
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


def verify_token(token: str, expected_type: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != expected_type:
            return None

        return payload

    except JWTError:
        return None



# def verify_token(token: str, expected_type: str) -> Optional[str]:
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         print("✅ PAYLOAD:", payload)

#         token_type = payload.get("type")
#         subject = payload.get("sub")

#         if token_type != expected_type:
#             print("❌ TYPE MISMATCH:", token_type, expected_type)
#             return None

#         if not isinstance(subject, str):
#             return None

#         return subject

#     except JWTError as e:
#         print("🔥 JWT ERROR:", str(e))
#         return None
    


def hash_password(password: str):
    if len(password) > 72:
        raise HTTPException(status_code=400, detail="Password too long")
    return pwd_context.hash(password)



def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password[:72], hashed_password)



def reset_password(db: Session, token: str, new_password: str):

    # 1️⃣ Verify token
    payload = verify_token(token, expected_type="reset")

    if not payload:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    email = payload.get("sub")
    token_pwd_at = payload.get("pwd_at")

    if not email:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    # 2️⃣ Get user
    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 3️⃣ ✅ FIX: Compare timestamps safely
    user_pwd_at = int(user.password_updated_at.timestamp()) if user.password_updated_at else 0 # type: ignore

    if abs(user_pwd_at - int(token_pwd_at)) > 5: # type: ignore
        raise HTTPException(status_code=400, detail="Token already used")

    # 4️⃣ Prevent same password reuse
    if verify_password(new_password, user.password): # type: ignore
        raise HTTPException(
            status_code=400,
            detail="New password cannot be same as old password"
        )

    # 5️⃣ Update password
    user.password = hash_password(new_password) # type: ignore
    user.password_updated_at = datetime.now(timezone.utc) # type: ignore

    db.commit()
    db.refresh(user)

    return {"message": "Password reset successful"}