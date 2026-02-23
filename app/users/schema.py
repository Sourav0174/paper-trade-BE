from pydantic import BaseModel, EmailStr
from datetime import datetime
from pydantic import BaseModel
from datetime import datetime
from app.users.models import SubscriptionEnum

class UserCreate(BaseModel):
    name: str
    gender: str
    email: EmailStr
    password: str

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

# class UserResponse(BaseModel):
#     id: int
#     name: str
#     gender: str
#     email: EmailStr
#     is_subscribed: bool
#     created_at: datetime

#     class Config:
#         from_attributes = True
