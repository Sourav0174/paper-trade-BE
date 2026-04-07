from sqlalchemy import Column, Integer, Float, String, DateTime
from datetime import datetime
from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)

    symbol = Column(String, index=True)
    quantity = Column(Integer)
    price = Column(Float)

    trade_type = Column(String)  # BUY / SELL

    created_at = Column(DateTime, default=datetime.utcnow)