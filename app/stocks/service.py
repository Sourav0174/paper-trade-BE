
from typing import List, Dict, Tuple
from app.stocks.schema import StockResponse, StockFilterEnum
import yfinance as yf

import pandas as pd
import yfinance as yf


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
def fetch_real_price(symbol: str):
    try:
        stock = yf.Ticker(symbol + ".NS")  # NSE stocks

        data = stock.history(period="5d")

        if data.empty:
            return 0, 0

        latest = data.iloc[-1]

        value = data["Close"].iloc[-1]
        open_price = data["Open"].iloc[-1]

        change = round(((value - open_price) / open_price) * 100, 2)

        return value, change

    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return 0, 0





def fetch_multiple_prices(symbols: list[str]) -> Dict[str, Tuple[float, float]]:
    if not symbols:
        return {}

    try:
        tickers = yf.download(
            tickers=" ".join([s + ".NS" for s in symbols]),
            period="1d",
            group_by="ticker",
            threads=True
        )

        print("Tickers Response:\n", tickers)

        if tickers is None or len(tickers) == 0:
            return {s: (0, 0) for s in symbols}

    except Exception as e:
        print(f"Download error: {e}")
        return {s: (0, 0) for s in symbols}

    result: Dict[str, Tuple[float, float]] = {}

    for symbol in symbols:
        key = symbol + ".NS"

        try:
            if len(symbols) == 1:
                data = tickers
            else:
                # FIX: MultiIndex handling
                if isinstance(tickers.columns, pd.MultiIndex):
                    data = tickers[key]
                else:
                    data = tickers

            if data.empty:
                raise ValueError("Empty Data")

            value = round(float(data["Close"].iloc[-1]), 2)
            open_price = float(data["Open"].iloc[-1])

            change = round(((value - open_price) / open_price) * 100, 2)

            result[symbol] = (value, change)

        except Exception as e:
            print(f"❌ ERROR for {symbol}: {e}")
            result[symbol] = (0, 0)
    return result


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

    if not paginated:
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": []
        }

    result: List[StockResponse] = []

    symbols = [stock["symbol"] for stock in paginated]
    price_map = fetch_multiple_prices(symbols)


    for stock in paginated:
        value, change = price_map.get(stock["symbol"], (0, 0))

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


print(fetch_real_price("RELIANCE"))