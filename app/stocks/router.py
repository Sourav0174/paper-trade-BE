from fastapi import APIRouter, Query

from app.stocks.schema import PaginatedStockResponse

from app.stocks.service import get_market_status, get_stocks

router = APIRouter(
    prefix="/market",
    tags=["Market"],
)


@router.get(
    "/stocks",
    response_model=PaginatedStockResponse,
)
def fetch_stocks(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
):
    return get_stocks(
        page=page,
        limit=limit,
        search=search,
    )

@router.get("/status")
def market_status():
    return {
        "marketStatus": get_market_status()
    }