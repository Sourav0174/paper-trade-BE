from enum import Enum
from typing import List

from pydantic import BaseModel


class StockFilterEnum(str, Enum):
    NIFTY_50 = "NIFTY_50"
    NIFTY_BANK = "NIFTY_BANK"
    SENSEX = "SENSEX"
    ALL = "ALL"


class SortEnum(str, Enum):
    DEFAULT = "DEFAULT"
    TOP_GAINERS = "TOP_GAINERS"
    TOP_LOSERS = "TOP_LOSERS"


class StockResponse(BaseModel):
    symbol: str
    name: str
    exchange: str

    currentPrice: float

    changeValue: float
    changePercent: float

    isUp: bool


class PaginatedStockResponse(BaseModel):
    marketStatus: str

    total: int
    page: int
    limit: int

    totalPages: int

    hasNext: bool
    hasPrevious: bool

    data: List[StockResponse]