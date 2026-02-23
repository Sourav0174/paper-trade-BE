from sqlalchemy.orm import Session
from app.users.models import SubscriptionEnum, User
from app.core.security import hash_password, verify_password, create_access_token
from fastapi import HTTPException

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from app.database import get_db
from app.core.security import verify_token
from app.core.security import create_verification_token
from app.core.email import send_verification_email


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")




def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
):
    user_id = verify_token(token, expected_type="access")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user



def create_user(db: Session, name: str, gender: str, email: str, password: str):
    hashed = hash_password(password)

    user = User(
        name=name,
        gender=gender,
        email=email,
        password=hashed,
        subscription=SubscriptionEnum.FREE,
        is_verified=False
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    email_str = str(user.email)

    token = create_verification_token(email_str)
    print("CREATED TOKEN:", token)
    send_verification_email(email_str, token)

    return user


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return None

    if not verify_password(password, str(user.password)):
        return None

    if user.is_verified is not True:

        raise HTTPException(status_code=403, detail="Email not verified")

    return user



def login_user(db: Session, email: str, password: str):
    user = authenticate_user(db, email, password)
    if not user:
        return None
    token = create_access_token(str(user.id))

    return token
