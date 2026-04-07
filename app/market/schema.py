from pydantic import BaseModel


class MarketIndex(BaseModel):
    name: str
    value: float
    changePercent: float
    isUp: bool