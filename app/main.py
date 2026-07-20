from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.trades.router import router as trade_router
from app.database import engine
from sqlalchemy import text
from app.users.models import User
from app.users.router import router as user_router
from app.market.router import router as market_router
from app.stocks.router import router as stocks_router
from app.trades.router import router as trade_router
from app.subscriptions.router import router as subscription_router
from app.chart.router import router as chart_router

from app.trades.router import router as trade_router
from app.market.router import router as market_router
from app.stocks.router import router as stock_router
from app.performance.router import router as performance_router
from app.trades.scheduler import start_scheduler, shutdown_scheduler


User.metadata.create_all(bind=engine)
from app.trades.models import Trade

Trade.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(lifespan=lifespan)

app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(trade_router)
app.include_router(market_router)
app.include_router(stocks_router)
app.include_router(subscription_router)
app.include_router(chart_router)
app.include_router(performance_router)

@app.get("/")
def root():
    return {"message": "PaperTrade Backend Running!"}
