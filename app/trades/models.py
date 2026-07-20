from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.trades.enums import OrderStatus, OrderType, TradeType


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

    # Shares locked by pending SELL limit orders. Available-to-sell = quantity - reserved_quantity.
    reserved_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0
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

    # Cash locked by pending BUY limit orders. Available-to-spend = available_balance.
    reserved_balance: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_id_status", "user_id", "status"),
        Index("ix_orders_symbol_status", "symbol", "status"),
    )

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

    trade_type: Mapped[TradeType] = mapped_column(
        Enum(TradeType, name="order_trade_type")
    )

    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type")
    )

    # Null for MARKET orders.
    limit_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"),
        default=OrderStatus.PENDING,
        index=True
    )

    executed_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    # Cash reserved for BUY limit orders (limit_price * quantity). Unused for SELL,
    # whose reservation is tracked as Holding.reserved_quantity instead.
    reserved_amount: Mapped[float] = mapped_column(
        Float,
        default=0.0
    )

    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    # Source of truth for day-order expiry: same day's market close, in UTC.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True
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