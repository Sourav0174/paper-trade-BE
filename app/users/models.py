from sqlalchemy import Column, Integer, String, Enum, DateTime, Boolean
from sqlalchemy.sql import func
import enum
from app.database import Base


class GenderEnum(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class SubscriptionEnum(str, enum.Enum):
    FREE = "FREE"
    PRO = "PRO"
    PREMIUM = "PREMIUM"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    gender = Column(Enum(GenderEnum), nullable=True)
    password = Column(String, nullable=False)

    is_verified = Column(Boolean, default=False, nullable=False)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)

    subscription = Column(
        Enum(SubscriptionEnum),
        default=SubscriptionEnum.FREE,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )