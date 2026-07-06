from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.performance.schema import (
    PortfolioPerformanceResponse,
    PerformancePeriod,
)
from app.performance.service import performance_service
from app.users.service import get_current_user

router = APIRouter(
    prefix="/performance",
    tags=["Performance"],
)


@router.get(
    "/portfolio",
    response_model=PortfolioPerformanceResponse,
)
async def get_portfolio_performance(
    period: PerformancePeriod = PerformancePeriod.WEEK,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return await performance_service.get_portfolio_performance(
        db=db,
        user_id=current_user.id,
        period=period,
    )