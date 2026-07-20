from typing import Optional

from fastapi import APIRouter, Query

from app.chart.schemas import ChartResponseSchema
from app.chart.service import chart_service

router = APIRouter(
    prefix="/chart",
    tags=["Chart"]
)

DEFAULT_CANDLE_LIMIT = 300
MAX_CANDLE_LIMIT = 1000


@router.get(
    "",
    response_model=ChartResponseSchema
)
async def get_chart(
    symbol: str = Query(..., min_length=1),
    timeframe: str = "1D",
    limit: int = Query(DEFAULT_CANDLE_LIMIT, ge=1, le=MAX_CANDLE_LIMIT),
    before: Optional[int] = Query(
        None,
        description=(
            "Unix timestamp (seconds). Returns the `limit` candles "
            "immediately preceding this time, for loading older history. "
            "Omit to get the most recent candles."
        ),
    ),
):

    return await chart_service.get_chart_data(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        before=before,
    )

@router.get("/price/{symbol}")
async def get_price(symbol: str):

    price = await chart_service.get_live_price(
        symbol
    )

    return {
        "symbol": symbol.upper(),
        "price": price,
    }
