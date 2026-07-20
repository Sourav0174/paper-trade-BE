from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.trades.enums import OrderStatus, OrderType, TradeType
from app.trades.models import Holding, Order, Portfolio
from app.trades.schema import OrderCreate
from app.trades.service import trade_service
from app.stocks.service import fetch_single_price, get_market_status
from app.users.models import User

LIMIT_PRICE_BAND_PERCENT = 10


class OrderService:
    """Order lifecycle: creation, validation, reservation, cancellation, and
    the safe execution entrypoint used by the scheduler. Ledger mutations
    (the actual money/holdings math) stay in TradeService.execute_order()."""

    def create_order(self, db: Session, user_id: int, data: OrderCreate) -> Order:

        if get_market_status() != "OPEN":
            raise HTTPException(
                status_code=400,
                detail="Market is closed. Orders can only be placed during market hours."
            )

        symbol = data.symbol.upper().strip()

        live_price = fetch_single_price(symbol)

        if live_price is None or live_price <= 0:
            raise HTTPException(
                status_code=400,
                detail="Unable to fetch live price."
            )

        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        trade_service.check_free_user_buy_cap(db, user, data.trade_type)

        if data.order_type == OrderType.MARKET:
            return self._create_market_order(db, user_id, symbol, data, live_price)

        return self._create_limit_order(db, user_id, symbol, data, live_price)

    def _create_market_order(
        self,
        db: Session,
        user_id: int,
        symbol: str,
        data: OrderCreate,
        live_price: float,
    ) -> Order:

        order = Order(
            user_id=user_id,
            symbol=symbol,
            quantity=data.quantity,
            trade_type=data.trade_type,
            order_type=OrderType.MARKET,
            status=OrderStatus.PENDING,
        )
        db.add(order)
        db.flush()

        trade_service.execute_order(
            db,
            user_id,
            symbol,
            data.quantity,
            data.trade_type,
            live_price,
            order=order,
        )

        db.refresh(order)
        return order

    def _create_limit_order(
        self,
        db: Session,
        user_id: int,
        symbol: str,
        data: OrderCreate,
        live_price: float,
    ) -> Order:

        self._validate_limit_price_band(data.limit_price, live_price)

        portfolio = (
            db.query(Portfolio)
            .filter(Portfolio.user_id == user_id)
            .first()
        )

        if not portfolio:
            portfolio = Portfolio(user_id=user_id)
            db.add(portfolio)
            db.flush()

        holding = (
            db.query(Holding)
            .filter(
                Holding.user_id == user_id,
                Holding.symbol == symbol,
            )
            .first()
        )

        reserved_amount = 0.0

        if data.trade_type == TradeType.BUY:
            reserved_amount = data.limit_price * data.quantity
            self._reserve_funds(portfolio, reserved_amount)
        else:
            self._reserve_shares(holding, data.quantity)

        order = Order(
            user_id=user_id,
            symbol=symbol,
            quantity=data.quantity,
            trade_type=data.trade_type,
            order_type=OrderType.LIMIT,
            limit_price=data.limit_price,
            status=OrderStatus.PENDING,
            reserved_amount=reserved_amount,
            expires_at=self._market_close_today_utc(),
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        return order

    # ====================================
    # 🔹 CANCEL ORDER
    # Row-locks the order so a concurrent cancel/scheduler-execute can't act
    # on it twice, then only releases the reservation and flips status while
    # it's still PENDING - retrying a cancel is a safe no-op past that point.
    # ====================================
    def cancel_order(self, db: Session, user_id: int, order_id: int) -> Order:

        order = (
            db.query(Order)
            .filter(Order.id == order_id, Order.user_id == user_id)
            .with_for_update()
            .first()
        )

        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status != OrderStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Order is already {order.status.value} and cannot be cancelled",
            )

        if order.order_type == OrderType.LIMIT:
            portfolio, holding = self._lock_portfolio_and_holding(db, order)
            trade_service.release_reservation(portfolio, holding, order)

        order.status = OrderStatus.CANCELLED
        db.commit()
        db.refresh(order)

        return order

    def cancel_all_pending_for_user(self, db: Session, user_id: int) -> None:
        """Used by portfolio reset: cancels every PENDING order for the user,
        releasing all reservations before the portfolio/holdings are wiped."""

        pending_order_ids = [
            order_id
            for (order_id,) in (
                db.query(Order.id)
                .filter(Order.user_id == user_id, Order.status == OrderStatus.PENDING)
                .all()
            )
        ]

        for order_id in pending_order_ids:
            self.cancel_order(db, user_id, order_id)

    def list_orders(
        self,
        db: Session,
        user_id: int,
        status: OrderStatus | None = None,
    ) -> list[Order]:

        query = db.query(Order).filter(Order.user_id == user_id)

        if status is not None:
            query = query.filter(Order.status == status)

        return query.order_by(Order.created_at.desc()).all()

    def expire_order(self, db: Session, order_id: int) -> Order | None:
        """Scheduler-internal counterpart to cancel_order: no HTTP context, so a
        non-PENDING order is a silent idempotent no-op rather than a raised error."""

        order = (
            db.query(Order)
            .filter(Order.id == order_id)
            .with_for_update()
            .first()
        )

        if order is None or order.status != OrderStatus.PENDING:
            return order

        if order.order_type == OrderType.LIMIT:
            portfolio, holding = self._lock_portfolio_and_holding(db, order)
            trade_service.release_reservation(portfolio, holding, order)

        order.status = OrderStatus.EXPIRED
        db.commit()
        db.refresh(order)

        return order

    def _lock_portfolio_and_holding(
        self,
        db: Session,
        order: Order,
    ) -> tuple[Portfolio, Holding | None]:

        portfolio = (
            db.query(Portfolio)
            .filter(Portfolio.user_id == order.user_id)
            .with_for_update()
            .first()
        )

        holding = (
            db.query(Holding)
            .filter(
                Holding.user_id == order.user_id,
                Holding.symbol == order.symbol,
            )
            .with_for_update()
            .first()
        )

        return portfolio, holding

    def _validate_limit_price_band(self, limit_price: float, live_price: float) -> None:

        lower_bound = live_price * (1 - LIMIT_PRICE_BAND_PERCENT / 100)
        upper_bound = live_price * (1 + LIMIT_PRICE_BAND_PERCENT / 100)

        if not (lower_bound <= limit_price <= upper_bound):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Limit price must be within {LIMIT_PRICE_BAND_PERCENT}% of the "
                    f"current price ({round(live_price, 2)}). Allowed range: "
                    f"{round(lower_bound, 2)} - {round(upper_bound, 2)}."
                ),
            )

    def _reserve_funds(self, portfolio: Portfolio, amount: float) -> None:

        if portfolio.available_balance < amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        portfolio.available_balance -= amount
        portfolio.reserved_balance += amount

    def _reserve_shares(self, holding: Holding | None, quantity: int) -> None:

        available_quantity = (
            holding.quantity - holding.reserved_quantity if holding else 0
        )

        if not holding or available_quantity < quantity:
            raise HTTPException(status_code=400, detail="Not enough shares to sell")

        holding.reserved_quantity += quantity

    def _market_close_today_utc(self) -> datetime:

        ist = ZoneInfo("Asia/Kolkata")
        today_ist = datetime.now(ist).date()
        close_ist = datetime.combine(today_ist, time(15, 30), tzinfo=ist)

        return close_ist.astimezone(timezone.utc).replace(tzinfo=None)

    # ====================================
    # 🔹 EXECUTE PENDING ORDER (scheduler entrypoint)
    # Row-locks the order so a retried/concurrent scheduler tick can't act on
    # it twice, then re-checks it's still eligible before handing off to
    # TradeService.execute_order(). Orders that fail revalidation are
    # rejected rather than silently skipped, releasing their reservation.
    # ====================================
    def execute_pending_order(self, db: Session, order_id: int, live_price: float) -> Order | None:

        order = (
            db.query(Order)
            .filter(Order.id == order_id)
            .with_for_update()
            .first()
        )

        if order is None:
            return None

        if order.status != OrderStatus.PENDING:
            return order

        if not self._is_still_executable(order):
            self._reject_order(db, order)
            return order

        trade_service.execute_order(
            db,
            order.user_id,
            order.symbol,
            order.quantity,
            order.trade_type,
            live_price,
            order=order,
        )

        return order

    def _is_still_executable(self, order: Order) -> bool:

        if order.status != OrderStatus.PENDING:
            return False

        if order.expires_at is not None and datetime.utcnow() >= order.expires_at:
            return False

        if order.quantity <= 0:
            return False

        if order.order_type == OrderType.LIMIT and (
            order.limit_price is None or order.limit_price <= 0
        ):
            return False

        return True

    def _reject_order(self, db: Session, order: Order) -> None:

        if order.order_type == OrderType.LIMIT:
            portfolio, holding = self._lock_portfolio_and_holding(db, order)
            trade_service.release_reservation(portfolio, holding, order)

        order.status = OrderStatus.REJECTED
        db.commit()


order_service = OrderService()
