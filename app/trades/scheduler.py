import logging
import os
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import SessionLocal
from app.stocks.service import fetch_single_price, get_market_status
from app.trades.enums import OrderStatus, OrderType, TradeType
from app.trades.models import Order
from app.trades.order_service import order_service

logger = logging.getLogger(__name__)

EXECUTION_BATCH_SIZE = int(os.getenv("ORDER_EXECUTION_BATCH_SIZE", "50"))
EXPIRY_BATCH_SIZE = int(os.getenv("ORDER_EXPIRY_BATCH_SIZE", "100"))
SCHEDULER_INTERVAL_SECONDS = int(os.getenv("ORDER_SCHEDULER_INTERVAL_SECONDS", "15"))

EXECUTE_JOB_ID = "execute_pending_orders"
EXPIRE_JOB_ID = "expire_stale_orders"

_scheduler: AsyncIOScheduler | None = None


def _is_fillable(order: Order, live_price: float) -> bool:
    if order.trade_type == TradeType.BUY:
        return live_price <= order.limit_price
    return live_price >= order.limit_price


def execute_pending_orders_job() -> None:
    """One batch per tick, oldest first. Each order executes through the
    existing execute_pending_order() path, which owns locking, revalidation,
    and idempotency - this job only decides which orders are worth attempting."""

    if get_market_status() != "OPEN":
        return

    db = SessionLocal()

    try:
        orders = (
            db.query(Order)
            .filter(
                Order.status == OrderStatus.PENDING,
                Order.order_type == OrderType.LIMIT,
            )
            .order_by(Order.created_at.asc())
            .limit(EXECUTION_BATCH_SIZE)
            .all()
        )

        for order in orders:
            try:
                live_price = fetch_single_price(order.symbol)

                if live_price is None or live_price <= 0:
                    continue

                if _is_fillable(order, live_price):
                    order_service.execute_pending_order(db, order.id, live_price)

            except Exception:
                db.rollback()
                logger.exception("Failed to execute pending order %s", order.id)

    finally:
        db.close()


def expire_stale_orders_job() -> None:
    """One batch per tick, oldest first. expires_at is the sole source of
    truth for expiry, so this runs independently of market hours."""

    db = SessionLocal()

    try:
        now = datetime.utcnow()

        orders = (
            db.query(Order)
            .filter(
                Order.status == OrderStatus.PENDING,
                Order.expires_at.isnot(None),
                Order.expires_at <= now,
            )
            .order_by(Order.created_at.asc())
            .limit(EXPIRY_BATCH_SIZE)
            .all()
        )

        for order in orders:
            try:
                order_service.expire_order(db, order.id)

            except Exception:
                db.rollback()
                logger.exception("Failed to expire order %s", order.id)

    finally:
        db.close()


def get_scheduler() -> AsyncIOScheduler:
    """Module-level singleton: repeated calls (e.g. a re-triggered lifespan
    startup) always return the same scheduler instead of instantiating a new one."""

    global _scheduler

    if _scheduler is None:
        _scheduler = AsyncIOScheduler()

        _scheduler.add_job(
            execute_pending_orders_job,
            "interval",
            seconds=SCHEDULER_INTERVAL_SECONDS,
            id=EXECUTE_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        _scheduler.add_job(
            expire_stale_orders_job,
            "interval",
            seconds=SCHEDULER_INTERVAL_SECONDS,
            id=EXPIRE_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    return _scheduler


def start_scheduler() -> None:
    scheduler = get_scheduler()

    if not scheduler.running:
        scheduler.start()
        logger.info(
            "Order scheduler started (interval=%ss, execution_batch=%s, expiry_batch=%s)",
            SCHEDULER_INTERVAL_SECONDS,
            EXECUTION_BATCH_SIZE,
            EXPIRY_BATCH_SIZE,
        )


def shutdown_scheduler() -> None:
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Order scheduler stopped")
