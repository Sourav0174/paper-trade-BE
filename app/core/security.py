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

# SECRET_KEY = "supersecretkey"
SECRET_KEY: str = os.environ["SECRET_KEY"]





if SECRET_KEY is None:
    raise ValueError("SECRET_KEY is not set in environment variables")


  # later move to .env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def verify_token(token: str) -> Optional[str]:
    
    try:
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if not isinstance(user_id, str):
            return None

        return user_id
    except JWTError:
        return None



def hash_password(password: str):
    return pwd_context.hash(password[:72])



def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password[:72], hashed_password)



def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
