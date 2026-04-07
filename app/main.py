from fastapi import FastAPI
from app.trades.router import router as trade_router
from app.database import engine
from sqlalchemy import text
from app.users.models import User
from app.users.router import router as user_router
from app.market.router import router as market_router
from app.stocks.router import router as stocks_router
from app.trades.router import router as trade_router



User.metadata.create_all(bind=engine)
from app.trades.models import Trade

Trade.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(trade_router)
app.include_router(market_router)
app.include_router(stocks_router)

@app.get("/")
def root():
    return {"message": "PaperTrade Backend Running 🚀"}
