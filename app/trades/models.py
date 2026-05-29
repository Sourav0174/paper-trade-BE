from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        index=True
    )

    symbol: Mapped[str] = mapped_column(
        String,
        index=True
    )

    quantity: Mapped[int] = mapped_column(Integer)

    price: Mapped[float] = mapped_column(Float)

    trade_type: Mapped[str] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        index=True
    )

    symbol: Mapped[str] = mapped_column(
        String,
        index=True
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        default=0
    )

    avg_price: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    invested_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    realized_pnl: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True
    )

    total_balance: Mapped[float] = mapped_column(
        Float,
        default=100000.0
    )

    available_balance: Mapped[float] = mapped_column(
        Float,
        default=100000.0
    )

    invested_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    realized_pnl: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )