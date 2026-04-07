import random
from typing import List
from app.stocks.schema import StockResponse, StockFilterEnum


# Mock stock groups
NIFTY_50_STOCKS = [
    {"name": "Reliance Industries", "symbol": "RELIANCE"},
    {"name": "HDFC Bank", "symbol": "HDFCBANK"},
    {"name": "Infosys", "symbol": "INFY"},
]

NIFTY_BANK_STOCKS = [
    {"name": "ICICI Bank", "symbol": "ICICIBANK"},
    {"name": "Axis Bank", "symbol": "AXISBANK"},
]

SENSEX_STOCKS = [
    {"name": "TCS", "symbol": "TCS"},
    {"name": "ITC", "symbol": "ITC"},
]

ALL_STOCKS = (
    NIFTY_50_STOCKS +
    NIFTY_BANK_STOCKS +
    SENSEX_STOCKS
)


def generate_mock_price():
    value = round(random.uniform(100, 3000), 2)
    change = round(random.uniform(-3, 3), 2)

    return value, change


def get_stocks(index: StockFilterEnum, page: int, limit: int, search: str | None = None):

    # Select group
    if index == StockFilterEnum.NIFTY_50:
        stocks = NIFTY_50_STOCKS
    elif index == StockFilterEnum.NIFTY_BANK:
        stocks = NIFTY_BANK_STOCKS
    elif index == StockFilterEnum.SENSEX:
        stocks = SENSEX_STOCKS
    else:
        stocks = ALL_STOCKS

    # 🔎 Apply Search (Before Pagination)
    if search:
        search_lower = search.lower()

        stocks = [
            stock for stock in stocks
            if search_lower in stock["name"].lower()
            or search_lower in stock["symbol"].lower()
        ]

    total = len(stocks)

    # Pagination
    start = (page - 1) * limit
    end = start + limit
    paginated = stocks[start:end]

    result: List[StockResponse] = []

    for stock in paginated:
        value, change = generate_mock_price()

        result.append(
            StockResponse(
                name=stock["name"],
                symbol=stock["symbol"],
                value=value,
                changePercent=change,
                isUp=change >= 0
            )
        )

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "data": result
    }

    if index == StockFilterEnum.NIFTY_50:
        stocks = NIFTY_50_STOCKS
    elif index == StockFilterEnum.NIFTY_BANK:
        stocks = NIFTY_BANK_STOCKS
    elif index == StockFilterEnum.SENSEX:
        stocks = SENSEX_STOCKS
    else:
        stocks = ALL_STOCKS

    total = len(stocks)

    # Pagination logic
    start = (page - 1) * limit
    end = start + limit
    paginated = stocks[start:end]

    result: List[StockResponse] = []

    for stock in paginated:
        value, change = generate_mock_price()

        result.append(
            StockResponse(
                name=stock["name"],
                symbol=stock["symbol"],
                value=value,
                changePercent=change,
                isUp=change >= 0
            )
        )

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "data": result
    }