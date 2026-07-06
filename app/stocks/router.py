from fastapi import APIRouter, Query

from app.stocks.schema import (
    PaginatedStockResponse,
    StockFilterEnum,
    SortEnum,
)

from app.stocks.service import get_stocks

router = APIRouter(
    prefix="/market",
    tags=["Market"],
)


@router.get(
    "/stocks",
    response_model=PaginatedStockResponse,
)
def fetch_stocks(
    index: StockFilterEnum = Query(StockFilterEnum.ALL),
    sort: SortEnum = Query(SortEnum.DEFAULT),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
):
    return get_stocks(
        index=index,
        sort=sort,
        page=page,
        limit=limit,
        search=search,
    )