from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.trades.enums import OrderStatus
from app.trades.service import trade_service
from app.trades.order_service import order_service
from app.trades.schema import OrderCreate, OrderResponse, TradeCreate
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
async def get_holdings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await trade_service.get_holdings(
        db,
        current_user.id
    )

@router.get("/portfolio")
async def get_portfolio(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await trade_service.get_portfolio(
        db,
        current_user.id
    )

@router.post("/reset")
def reset_portfolio(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Pending orders must be cancelled (releasing their reservations) before
    # the portfolio/holdings they reserved against are wiped.
    order_service.cancel_all_pending_for_user(db, current_user.id)

    return trade_service.reset_portfolio(
        db,
        current_user.id
    )


@router.get("/")
def get_trades(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return trade_service.get_trades(db, current_user.id)


@router.post("/orders", response_model=OrderResponse)
def create_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return order_service.create_order(db, current_user.id, data)


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(
    status: OrderStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return order_service.list_orders(db, current_user.id, status)


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return order_service.cancel_order(db, current_user.id, order_id)