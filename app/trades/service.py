from sqlalchemy.orm import Session
from app.trades.models import Trade
from app.trades.schema import TradeType


class TradeService:

    def create_trade(self, db: Session, user_id: int, data):

        symbol = data.symbol.upper().strip()

        # 🔹 Calculate current holdings
        trades = db.query(Trade).filter(
            Trade.user_id == user_id,
            Trade.symbol == symbol
        ).all()

        total_quantity = 0

        for t in trades:
            if str(t.trade_type) == TradeType.BUY.value:
                total_quantity += t.quantity
            elif str(t.trade_type) == TradeType.SELL.value:
                total_quantity -= t.quantity

        # 🔹 SELL validation
        if data.trade_type == TradeType.SELL and data.quantity > total_quantity:
            raise Exception("Not enough shares to sell")

        # 🔹 Create trade
        trade = Trade(
            user_id=user_id,
            symbol=symbol,
            quantity=data.quantity,
            price=data.price,
            trade_type=data.trade_type.value   # ✅ IMPORTANT FIX
        )

        db.add(trade)
        db.commit()
        db.refresh(trade)

        return trade


    # ✅ ADD THIS METHOD
    def get_trades(self, db: Session, user_id: int):
        return db.query(Trade).filter(Trade.user_id == user_id).all()
    
    def get_holdings(self, db: Session, user_id: int):
            trades = db.query(Trade).filter(Trade.user_id == user_id).all()

            holdings = {}

            # 🔹 Aggregate trades
            for trade in trades:
                symbol = trade.symbol

                if symbol not in holdings:
                    holdings[symbol] = {
                        "quantity": 0,
                        "total_cost": 0
                    }

                if str(trade.trade_type) == TradeType.BUY.value:
                    holdings[symbol]["quantity"] += trade.quantity
                    holdings[symbol]["total_cost"] += trade.quantity * trade.price

                elif str(trade.trade_type) == TradeType.SELL.value:
                    holdings[symbol]["quantity"] -= trade.quantity

            result = []
            total_portfolio_value = 0

            # 🔹 Calculate values
            for symbol, data in holdings.items():
                quantity = data["quantity"]

                if quantity <= 0:
                    continue

                avg_price = data["total_cost"] / quantity
                current_price = avg_price * 1.1  # temp

                current_value = current_price * quantity
                total_portfolio_value += current_value

                pnl_value = (current_price - avg_price) * quantity
                pnl_percent = ((current_price - avg_price) / avg_price) * 100

                result.append({
                    "symbol": symbol,
                    "quantity": quantity,
                    "avg_price": round(avg_price, 2),
                    "current_price": round(current_price, 2),
                    "pnl_value": round(pnl_value, 2),
                    "pnl_percent": round(pnl_percent, 2),
                    "current_value": round(current_value, 2)
                })

            # 🔹 Calculate weight
            for item in result:
                if total_portfolio_value > 0:
                    item["weight"] = round(item["current_value"] / total_portfolio_value, 4)
                else:
                    item["weight"] = 0

                

            return result

trade_service = TradeService()