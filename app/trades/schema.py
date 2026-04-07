from pydantic import BaseModel, Field
from enum import Enum


class TradeType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeCreate(BaseModel):
    symbol: str
    quantity: int = Field(gt=0)   # must be > 0
    price: float = Field(gt=0)    # must be > 0
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