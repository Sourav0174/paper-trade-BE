from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from pydantic import BaseModel
from datetime import datetime
from app.users.models import SubscriptionEnum


class UserCreate(BaseModel):
    name: str
    gender: str
    email: EmailStr
    password: str

    @field_validator("password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.islower() for c in v):
            raise ValueError("Must include a lowercase letter")
        if not any(c.isupper() for c in v):
            raise ValueError("Must include an uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Must include a number")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str





class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    gender: str | None
    subscription: SubscriptionEnum
    created_at: datetime
    updated_at: datetime

    @property
    def is_subscribed(self) -> bool:
        return self.subscription != SubscriptionEnum.FREE

    class Config:
        from_attributes = True  # IMPORTANT for SQLAlchemy

class EmailRequest(BaseModel):
    email: EmailStr




class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str  

    @field_validator("new_password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not any(c.islower() for c in v):
            raise ValueError("Must include a lowercase letter")

        if not any(c.isupper() for c in v):
            raise ValueError("Must include an uppercase letter")

        if not any(c.isdigit() for c in v):
            raise ValueError("Must include a number")

        return v