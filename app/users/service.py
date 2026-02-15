from sqlalchemy.orm import Session
from app.users.models import User
from app.core.security import hash_password, verify_password, create_access_token

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from app.database import get_db
from app.core.security import verify_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
):
    user_id = verify_token(token)
    if not user_id:
        return None

    user = db.query(User).filter(User.id == int(user_id)).first()
    return user


def create_user(db: Session, email: str, password: str):
    hashed = hash_password(password)
    user = User(email=email, password=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, str(user.password)):
        return None
    return user


def login_user(db: Session, email: str, password: str):
    user = authenticate_user(db, email, password)
    if not user:
        return None
    token = create_access_token({"sub": str(user.id)})
    return token
