from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.users import service, schema
from app.users.models import User
from fastapi import Depends
from app.users.service import get_current_user

from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter()

@router.get("/me")
def get_me(current_user = Depends(get_current_user)):
    return current_user

@router.post("/signup", response_model=schema.UserResponse)
def signup(user: schema.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    return service.create_user(db, user.email, user.password)



@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    token = service.login_user(db, form_data.username, form_data.password)

    if not token:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {"access_token": token, "token_type": "bearer"}
