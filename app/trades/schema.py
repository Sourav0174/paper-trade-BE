from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.trades.enums import OrderStatus, OrderType, TradeType

__all__ = ["TradeType"]


class TradeCreate(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    trade_type: TradeType


class TradeResponse(BaseModel):
    id: int
    symbol: str
    quantity: int
    price: float
    trade_type: TradeType

    class Config:
        from_attributes = True

class HoldingResponse(BaseModel):
    symbol: str
    quantity: int
    avg_price: float
    current_price: float
    pnl_value: float
    pnl_percent: float
    weight: float


class OrderCreate(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)
    trade_type: TradeType
    order_type: OrderType
    limit_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_limit_price_presence(self):
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit_price is required for LIMIT orders")

        if self.order_type == OrderType.MARKET and self.limit_price is not None:
            raise ValueError("limit_price must not be set for MARKET orders")

        return self


class OrderResponse(BaseModel):
    id: int
    symbol: str
    quantity: int
    trade_type: TradeType
    order_type: OrderType
    limit_price: float | None
    status: OrderStatus
    executed_price: float | None
    executed_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True