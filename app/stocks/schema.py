from typing import List

from pydantic import BaseModel


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