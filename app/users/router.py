
from sqlalchemy.orm import Session
from starlette import status
from app.core.security import create_access_token, verify_token
from app.database import get_db
from app.users import service, schema
from app.users.models import User
from fastapi import APIRouter, Depends, HTTPException, Query
from app.users.service import get_current_user
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter()

@router.get("/me")
def get_me(current_user = Depends(get_current_user)):
    return current_user



@router.post("/signup")
def signup(user: schema.UserCreate, db: Session = Depends(get_db)):

    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    new_user = service.create_user(
        db,
        user.name,
        user.gender,
        user.email,
        user.password
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": "Account created successfully",
            "data": {
                "id": new_user.id,
                "email": new_user.email,
                "name": new_user.name,
                "gender": new_user.gender,
                "subscription": new_user.subscription,
                "created_at": str(new_user.created_at),
                "updated_at": str(new_user.updated_at),
            }
        }
    )


@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(token: str = Query(...), db: Session = Depends(get_db)):

    print("Received token:", token)


    # 🔐 Decode token and ensure it's verification type
    email = verify_token(token, expected_type="verify")


    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # 🔍 Find user
    user = db.query(User).filter(User.email == email).first()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_verified is True:
        return """
        <h2>Email already verified ✅</h2>
        """

    # ✅ Mark as verified
    setattr(user, "is_verified", True)

    db.commit()

    return """
    <h2>Email successfully verified 🎉</h2>
    <p>You can now log in to your account.</p>
    """




@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = service.authenticate_user(
        db,
        form_data.username,
        form_data.password
    )

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))

     
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "gender": user.gender,
            "email": user.email,
            "is_subscribed": user.subscription
        }
    }
