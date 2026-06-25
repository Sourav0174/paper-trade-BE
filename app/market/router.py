from fastapi import APIRouter
from app.market.service import market_service

router = APIRouter(prefix="/market", tags=["Market"])


@router.get("/indexes")
async def get_indexes():
    return await market_service.get_indexes()

@router.get("/price/{symbol}")
async def get_price(symbol: str):
    return {
        "symbol": symbol,
        "price": await market_service.get_stock_price(symbol)
    }