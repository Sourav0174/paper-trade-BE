from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.chart.service import chart_service
from app.trades.models import Holding, Portfolio, Trade
from app.trades.schema import TradeType
from app.stocks.service import fetch_single_price
import traceback


class TradeService:

    def create_trade(self, db: Session, user_id: int, data):

        symbol = data.symbol.upper().strip()

        # ⭐ Server decides execution price
        live_price = fetch_single_price(symbol)

        if live_price is None or live_price <= 0:
            raise HTTPException(
                status_code=400,
                detail="Unable to fetch live price."
            )

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

            if data.trade_type == TradeType.BUY:

                total_cost = live_price * data.quantity

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

                new_qty = holding.quantity + data.quantity

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

                if not holding or holding.quantity < data.quantity:
                    raise HTTPException(
                        status_code=400,
                        detail="Not enough shares to sell",
                    )

                sell_value = live_price * data.quantity

                realized_pnl = (
                    (live_price - holding.avg_price)
                    * data.quantity
                )

                holding.quantity -= data.quantity

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
                    data.quantity
                    * holding.avg_price
                )

            trade = Trade(
                user_id=user_id,
                symbol=symbol,
                quantity=data.quantity,
                price=live_price,
                trade_type=data.trade_type.value,
            )

            db.add(trade)

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

        net_worth = (
            float(portfolio.available_balance)
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

            else:

                portfolio = Portfolio(
                    user_id=user_id,
                    total_balance=100000.0,
                    available_balance=100000.0,
                    invested_amount=0.0,
                    realized_pnl=0.0
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
trade_service = TradeService()