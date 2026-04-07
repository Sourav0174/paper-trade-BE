from pydantic import BaseModel
from enum import Enum
from typing import List


class StockFilterEnum(str, Enum):
    NIFTY_50 = "NIFTY_50"
    NIFTY_BANK = "NIFTY_BANK"
    SENSEX = "SENSEX"
    ALL = "ALL"


class StockResponse(BaseModel):
    name: str
    symbol: str
    value: float
    changePercent: float
    isUp: bool


class PaginatedStockResponse(BaseModel):
    total: int
    page: int
    limit: int
    data: List[StockResponse]