from fastapi import APIRouter
from app.market.service import market_service

router = APIRouter(prefix="/market", tags=["Market"])


@router.get("/indexes")
async def get_indexes():
    return await market_service.get_indexes()