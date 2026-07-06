from enum import Enum
from typing import List

from pydantic import BaseModel


class PerformancePeriod(str, Enum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"


class PerformancePoint(BaseModel):
    label: str
    value: float


class PortfolioPerformanceResponse(BaseModel):
    period: PerformancePeriod

    currentValue: float

    pnl: float

    pnlPercent: float

    isPositive: bool

    history: List[PerformancePoint]