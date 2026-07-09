from fastapi import APIRouter, HTTPException, Query

from app.chart.schemas import ChartResponseSchema
from app.chart.service import chart_service

router = APIRouter(
    prefix="/chart",
    tags=["Chart"]
)


@router.get(
    "",
    response_model=ChartResponseSchema
)
async def get_chart(
    symbol: str = Query(..., min_length=1),
    timeframe: str = "1D",
):

    return await chart_service.get_chart_data(
        symbol=symbol,
        timeframe=timeframe,
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