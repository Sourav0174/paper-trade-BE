"""
SQLAlchemy ORM models for AI Mentor review persistence.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)

from app.database import Base


class MentorReview(Base):
    """
    Stores generated mentor review history and caching state per user.
    """

    __tablename__ = "mentor_reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    review_type = Column(String, nullable=False, default="DAILY", index=True)

    health_score = Column(Float, nullable=False)
    trading_grade = Column(String, nullable=False)

    summary_json = Column(JSON, nullable=False)
    response_json = Column(JSON, nullable=False)

    trade_count = Column(Integer, nullable=False, default=0)
    last_trade_id = Column(String, nullable=True, index=True)

    stale = Column(Boolean, nullable=False, default=False, index=True)
    generated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_mentor_reviews_user_type", "user_id", "review_type"),
    )
