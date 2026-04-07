from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.trades.service import trade_service
from app.trades.schema import TradeCreate
from app.users.service import get_current_user

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.post("/")
def create_trade(
    data: TradeCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return trade_service.create_trade(db, current_user.id, data)


@router.get("/holdings")
def get_holdings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return trade_service.get_holdings(db, current_user.id)


@router.get("/")
def get_trades(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return trade_service.get_trades(db, current_user.id)