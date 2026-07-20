from typing import List, Optional

from pydantic import BaseModel


class CandleSchema(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float


class ChartResponseSchema(BaseModel):
    symbol: str
    timeframe: str

    # Null on pagination responses (`before` provided) — the quote is only
    # meaningful relative to "now", so it's computed once on the initial,
    # non-paginated load and omitted on older-history pages.
    ltp: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None

    candles: List[CandleSchema]
    has_more: bool = False
