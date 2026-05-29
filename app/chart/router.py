from fastapi import APIRouter

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
    symbol: str,
    timeframe: str = "1D",
):

    return await chart_service.get_chart_data(
        symbol=symbol,
        timeframe=timeframe,
    ) 