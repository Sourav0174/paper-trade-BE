from pydantic import BaseModel
from typing import List


class CandleSchema(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class ChartResponseSchema(BaseModel):
    symbol: str
    timeframe: str

    ltp: float
    change: float
    change_percent: float

    candles: List[CandleSchema]