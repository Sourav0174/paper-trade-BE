from fastapi import FastAPI
from app.trades.router import router as trade_router
from app.database import engine
from sqlalchemy import text
from app.users.models import User
from app.users.router import router as user_router

User.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(user_router, prefix="/users", tags=["Users"])

app.include_router(trade_router, prefix="/trades", tags=["Trades"])





# @app.get("/")
# def test_db():
#     with engine.connect() as connection:
#         result = connection.execute(text("SELECT 1"))
#         return {"db_response": result.scalar()}

@app.get("/")
def root():
    return {"message": "PaperTrade Backend Running 🚀"}
