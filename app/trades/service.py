from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.trades.models import Holding, Order, Portfolio, Trade
from app.trades.enums import OrderStatus, OrderType, TradeType
from app.stocks.service import fetch_single_price
from app.stocks.service import get_market_status
from app.users.models import User, SubscriptionEnum
from datetime import datetime, time, timedelta, timezone
from sqlalchemy import func
import traceback


class TradeService:

    def create_trade(self, db: Session, user_id: int, data):

        if get_market_status() != "OPEN":
            raise HTTPException(
                status_code=400,
                detail="Market is closed. Orders can only be placed during market hours."
            )

        symbol = data.symbol.upper().strip()

        # ⭐ Server decides execution price
        live_price = fetch_single_price(symbol)

        if live_price is None or live_price <= 0:
            raise HTTPException(
                status_code=400,
                detail="Unable to fetch live price."
            )

        return self.execute_order(
            db,
            user_id,
            symbol,
            data.quantity,
            data.trade_type,
            live_price,
        )

    # ====================================
    # 🔹 EXECUTE ORDER
    # Single execution path for MARKET and LIMIT orders. `order` is the
    # originating Order row - present for both, but only LIMIT orders carry
    # a reservation to release before the fill is applied.
    # ====================================
    def execute_order(
        self,
        db: Session,
        user_id: int,
        symbol: str,
        quantity: int,
        trade_type: TradeType,
        live_price: float,
        order: Order | None = None,
    ) -> Trade:

        try:

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


            user = (
                db.query(User)
                .filter(User.id == user_id)
                .first()
            )

            if not user:
                raise HTTPException(
                    status_code=404,
                    detail="User not found"
                )

            # No Order was handed in - this is the legacy direct-execution path
            # (POST /trades/). Synthesize one so every execution, old endpoint
            # or new, is backed by an Order row, and apply the placement-time
            # checks OrderService would otherwise have already run.
            if order is None:
                self.check_free_user_buy_cap(db, user, trade_type)
                order = Order(
                    user_id=user_id,
                    symbol=symbol,
                    quantity=quantity,
                    trade_type=trade_type,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.PENDING,
                )
                db.add(order)

            elif order.order_type == OrderType.LIMIT:
                self.release_reservation(portfolio, holding, order)

            if trade_type == TradeType.BUY:

                total_cost = live_price * quantity

                if portfolio.available_balance < total_cost:
                    raise HTTPException(
                        status_code=400,
                        detail="Insufficient balance",
                    )

                if not holding:
                    holding = Holding(
                        user_id=user_id,
                        symbol=symbol,
                        quantity=0,
                        avg_price=0,
                        invested_amount=0,
                        realized_pnl=0,
                    )
                    db.add(holding)

                new_qty = holding.quantity + quantity

                holding.avg_price = (
                    (holding.quantity * holding.avg_price)
                    + total_cost
                ) / new_qty

                holding.quantity = new_qty

                holding.invested_amount = (
                    holding.quantity * holding.avg_price
                )

                portfolio.available_balance -= total_cost
                portfolio.invested_amount += total_cost

            else:

                # Available-to-sell excludes shares already locked by other
                # pending LIMIT sell orders.
                available_quantity = (
                    holding.quantity - holding.reserved_quantity
                    if holding else 0
                )

                if not holding or available_quantity < quantity:
                    raise HTTPException(
                        status_code=400,
                        detail="Not enough shares to sell",
                    )

                sell_value = live_price * quantity

                realized_pnl = (
                    (live_price - holding.avg_price)
                    * quantity
                )

                # Capture avg_price BEFORE it can be reset to 0 below,
                # so the portfolio-level invested_amount reduction is correct.
                sell_avg_price = holding.avg_price

                holding.quantity -= quantity

                if holding.quantity == 0:
                    holding.avg_price = 0
                    holding.invested_amount = 0
                else:
                    holding.invested_amount = (
                        holding.quantity
                        * holding.avg_price
                    )

                holding.realized_pnl += realized_pnl

                portfolio.available_balance += sell_value

                portfolio.realized_pnl += realized_pnl

                portfolio.invested_amount -= (
                    quantity
                    * sell_avg_price
                )

            trade = Trade(
                user_id=user_id,
                symbol=symbol,
                quantity=quantity,
                price=live_price,
                trade_type=trade_type.value,
            )

            db.add(trade)

            order.status = OrderStatus.EXECUTED
            order.executed_price = live_price
            order.executed_at = datetime.utcnow()
            db.add(order)

            db.commit()

            db.refresh(trade)

            return trade

        except HTTPException:
            db.rollback()
            raise

        # except Exception as e:
        #     db.rollback()
        #     raise HTTPException(
        #         status_code=500,
        #         detail=str(e),
        #     )

        except Exception:
            db.rollback()

            print("\n" + "=" * 80)
            traceback.print_exc()
            print("=" * 80 + "\n")

            raise

    def release_reservation(
        self,
        portfolio: Portfolio,
        holding: Holding | None,
        order: Order,
    ) -> None:
        """Returns cash/shares locked by a pending LIMIT order to the available pool."""

        if order.trade_type == TradeType.BUY:
            portfolio.reserved_balance -= order.reserved_amount
            portfolio.available_balance += order.reserved_amount
        elif holding is not None:
            holding.reserved_quantity -= order.quantity

    def check_free_user_buy_cap(
        self,
        db: Session,
        user: User,
        trade_type: TradeType,
    ) -> None:
        """Free-tier users may place at most 5 BUY orders per IST calendar day."""

        if trade_type != TradeType.BUY or user.subscription != SubscriptionEnum.FREE:  # type: ignore
            return

        ist = ZoneInfo("Asia/Kolkata")

        # Today's date in IST
        today_ist = datetime.now(ist).date()

        # Start/end of today in IST
        start_ist = datetime.combine(today_ist, time.min, tzinfo=ist)
        end_ist = start_ist + timedelta(days=1)

        # Convert to UTC and remove tzinfo because DB stores naive UTC
        start_utc = start_ist.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = end_ist.astimezone(timezone.utc).replace(tzinfo=None)

        buy_orders_today = (
            db.query(func.count(Order.id))
            .filter(
                Order.user_id == user.id,
                Order.trade_type == TradeType.BUY,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.EXECUTED]),
                Order.created_at >= start_utc,
                Order.created_at < end_utc,
            )
            .scalar()
        )

        if buy_orders_today >= 5:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "BUY_LIMIT_REACHED",
                    "message": "Free users can place only 5 buy orders per day. Upgrade to Premium for unlimited trading."
                }
            )

    # ====================================
    # 🔹 GET TRADES
    # ====================================
    def get_trades(self, db: Session, user_id: int):

        return db.query(Trade).filter(
            Trade.user_id == user_id
        ).all()

    # ====================================
    # 🔹 GET HOLDINGS
    # ====================================
    async def get_holdings(self, db: Session, user_id: int):

        holdings = db.query(Holding).filter(
            Holding.user_id == user_id,
            Holding.quantity > 0
        ).all()

        result = []

        total_portfolio_value = 0

        

        # 🔹 First pass
        for holding in holdings:


            # TEMP PRICE
            # current_price = float(holding.avg_price) * 1.1
            current_price = fetch_single_price(
                holding.symbol    
                )

            if current_price is None:
                current_price = float(holding.avg_price)

            current_value = (
                current_price * holding.quantity
            )
            print(

                f"""
                Symbol: {holding.symbol}
                Avg Price: {holding.avg_price}
                Live Price: {current_price}
                Quantity: {holding.quantity}
                PnL: {(current_price - holding.avg_price) * holding.quantity}
                """
            )

            pnl_value = (
                (current_price - holding.avg_price)
                * holding.quantity
            )

            pnl_percent = 0

            if holding.avg_price > 0:
                pnl_percent = (
                    (current_price - holding.avg_price)
                    / holding.avg_price
                ) * 100

            total_portfolio_value += current_value

            print(holding.symbol, current_price)

            result.append({
                "symbol": holding.symbol,
                "quantity": holding.quantity,
                "avg_price": round(holding.avg_price, 2),
                "current_price": round(current_price, 2),
                "current_value": round(current_value, 2),
                "pnl_value": round(pnl_value, 2),
                "pnl_percent": round(pnl_percent, 2)
            })

        # 🔹 Weight calculation
        for item in result:

            if total_portfolio_value > 0:
                item["weight"] = round(
                    item["current_value"]
                    / total_portfolio_value,
                    4
                )
            else:
                item["weight"] = 0

        return result

    # ====================================
    # 🔹 GET PORTFOLIO
    # ====================================
    async def get_portfolio(self, db: Session, user_id: int):

        # ================================
        # 🔹 GET PORTFOLIO
        # ================================
        portfolio = db.query(Portfolio).filter(
            Portfolio.user_id == user_id
        ).first()

        # ================================
        # 🔹 DEFAULT RESPONSE
        # ================================
        if not portfolio:
            return {
                "total_balance": 100000.0,
                "available_balance": 100000.0,
                "invested_amount": 0.0,
                "current_value": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "net_worth": 100000.0
            }

        # ================================
        # 🔹 GET HOLDINGS
        # ================================
        holdings = db.query(Holding).filter(
            Holding.user_id == user_id,
            Holding.quantity > 0
        ).all()

        current_value = 0.0

        # ================================
        # 🔹 CALCULATE CURRENT VALUE
        # ================================
        for holding in holdings:

            # TEMP MARKET PRICE
            current_price = fetch_single_price(holding.symbol)

            if current_price is None:
                current_price = float(holding.avg_price)

            current_value += (
                current_price
                * holding.quantity
            )

        # ================================
        # 🔹 PNL CALCULATIONS
        # ================================
        unrealized_pnl = (
            current_value
            - float(portfolio.invested_amount)
        )

        # Reserved cash (locked by pending BUY limit orders) is still user
        # equity, so it counts toward net worth alongside available cash.
        net_worth = (
            float(portfolio.available_balance)
            + float(portfolio.reserved_balance)
            + current_value
        )

        total_pnl = (
            float(portfolio.realized_pnl)
            + unrealized_pnl
        )

        # ================================
        # 🔹 FINAL RESPONSE
        # ================================
        return {
            "total_balance": round(
                float(portfolio.total_balance),
                2
            ),

            "available_balance": round(
                float(portfolio.available_balance),
                2
            ),

            "invested_amount": round(
                float(portfolio.invested_amount),
                2
            ),

            "current_value": round(
                current_value,
                2
            ),

            "realized_pnl": round(
                float(portfolio.realized_pnl),
                2
            ),

            "unrealized_pnl": round(
                unrealized_pnl,
                2
            ),

            "total_pnl": round(
                total_pnl,
                2
            ),

            "net_worth": round(
                net_worth,
                2
            )
        }


    def reset_portfolio(self, db: Session, user_id: int):

        try:

            # Delete trades
            # db.query(Trade).filter(
            #     Trade.user_id == user_id
            # ).delete()

            # Delete holdings
            db.query(Holding).filter(
                Holding.user_id == user_id
            ).delete()

            # Reset portfolio
            portfolio = db.query(Portfolio).filter(
                Portfolio.user_id == user_id
            ).first()

            if portfolio:

                portfolio.total_balance = 100000.0
                portfolio.available_balance = 100000.0
                portfolio.invested_amount = 0.0
                portfolio.realized_pnl = 0.0
                portfolio.reserved_balance = 0.0

            else:

                portfolio = Portfolio(
                    user_id=user_id,
                    total_balance=100000.0,
                    available_balance=100000.0,
                    invested_amount=0.0,
                    realized_pnl=0.0,
                    reserved_balance=0.0,
                )

                db.add(portfolio)

            db.commit()

            return {
                "message": "Portfolio reset successfully"
            }

        except Exception as e:

            db.rollback()

            raise HTTPException(
                status_code=500,
                detail=str(e)
            )
trade_service = trade_service = TradeService()