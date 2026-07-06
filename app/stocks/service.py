import logging
from typing import Dict, List, Tuple

import pandas as pd
import yfinance as yf

from app.stocks.schema import (
    SortEnum,
    StockFilterEnum,
    StockResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Mock Stock Data
# ---------------------------------------------------------

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
    NIFTY_50_STOCKS
    + NIFTY_BANK_STOCKS
    + SENSEX_STOCKS
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def get_market_status() -> str:
    """
    Temporary implementation.

    Later replace with NSE market timings.
    """
    return "OPEN"


def fetch_single_price(symbol: str):
    price, _ = fetch_real_price(symbol)
    print(f"Fetched price for {price}")

    if price <= 0:
        return None

    return round(float(price), 2)

def fetch_real_price(symbol: str):
    try:
        stock = yf.Ticker(symbol + ".NS")  # NSE stocks

        data = stock.history(period="5d")

        if data.empty:
            return 0, 0

        latest = data.iloc[-1]

        value = float(data["Close"].iloc[-1])
        open_price = float(data["Open"].iloc[-1])

        change = round(((value-open_price)/open_price)*100,2)

        return float(value), float(change)

    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return 0, 0


def fetch_multiple_prices(
    symbols: List[str],
) -> Dict[str, Tuple[float, float, float]]:
    """
    Returns

    {
        "RELIANCE": (
            currentPrice,
            changeValue,
            changePercent
        )
    }
    """

    if not symbols:
        return {}

    try:
        tickers = yf.download(
            tickers=" ".join([f"{s}.NS" for s in symbols]),
            period="5d",
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )

        if tickers is None or len(tickers) == 0:
            return {
                symbol: (0.0, 0.0, 0.0)
                for symbol in symbols
            }

    except Exception as e:
        logger.exception(e)

        return {
            symbol: (0.0, 0.0, 0.0)
            for symbol in symbols
        }

    result: Dict[str, Tuple[float, float, float]] = {}

    for symbol in symbols:

        key = f"{symbol}.NS"

        try:

            if len(symbols) == 1:
                data = tickers
            else:

                if isinstance(
                    tickers.columns,
                    pd.MultiIndex,
                ):
                    data = tickers[key]
                else:
                    data = tickers

            if data.empty:
                raise ValueError("No data")

            current_price = round(
                float(
                    data["Close"].iloc[-1]
                ),
                2,
            )

            if len(data) >= 2:
                previous_close = float(
                    data["Close"].iloc[-2]
                )
            else:
                previous_close = current_price

            change_value = round(
                current_price - previous_close,
                2,
            )

            if previous_close == 0:
                change_percent = 0.0
            else:
                change_percent = round(
                    (change_value / previous_close)
                    * 100,
                    2,
                )

            result[symbol] = (
                current_price,
                change_value,
                change_percent,
            )

        except Exception as e:

            logger.exception(e)

            result[symbol] = (
                0.0,
                0.0,
                0.0,
            )

    return result


# ---------------------------------------------------------
# Main Service
# ---------------------------------------------------------

def get_stocks(
    index: StockFilterEnum,
    sort: SortEnum,
    page: int,
    limit: int,
    search: str | None = None,
):
    """
    Fetch market stocks with

    - Filtering
    - Searching
    - Sorting
    - Pagination
    """

    # -----------------------------
    # Filter by Index
    # -----------------------------

    if index == StockFilterEnum.NIFTY_50:
        stocks = NIFTY_50_STOCKS.copy()

    elif index == StockFilterEnum.NIFTY_BANK:
        stocks = NIFTY_BANK_STOCKS.copy()

    elif index == StockFilterEnum.SENSEX:
        stocks = SENSEX_STOCKS.copy()

    else:
        stocks = ALL_STOCKS.copy()

    # -----------------------------
    # Search
    # -----------------------------

    if search:

        keyword = search.strip().lower()

        stocks = [
            stock
            for stock in stocks
            if keyword in stock["name"].lower()
            or keyword in stock["symbol"].lower()
        ]

    # -----------------------------
    # Fetch prices for ALL stocks
    # -----------------------------

    symbols = [
        stock["symbol"]
        for stock in stocks
    ]

    price_map = fetch_multiple_prices(symbols)

    stock_list = []

    for stock in stocks:

        current_price, change_value, change_percent = price_map.get(
            stock["symbol"],
            (0.0, 0.0, 0.0),
        )

        stock_list.append(
            {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "exchange": "NSE",

                "currentPrice": current_price,

                "changeValue": change_value,
                "changePercent": change_percent,

                "isUp": change_percent >= 0,
            }
        )

    # -----------------------------
    # Sorting
    # -----------------------------

    if sort == SortEnum.TOP_GAINERS:

        stock_list.sort(
            key=lambda x: x["changePercent"],
            reverse=True,
        )

    elif sort == SortEnum.TOP_LOSERS:

        stock_list.sort(
            key=lambda x: x["changePercent"],
        )

    else:

        stock_list.sort(
            key=lambda x: x["symbol"],
        )

    # -----------------------------
    # Pagination
    # -----------------------------

    total = len(stock_list)

    total_pages = max(
        (total + limit - 1) // limit,
        1,
    )

    start = (page - 1) * limit
    end = start + limit

    paginated = stock_list[start:end]

    result = [
        StockResponse(**stock)
        for stock in paginated
    ]

    # -----------------------------
    # Response
    # -----------------------------

    return {
        "marketStatus": get_market_status(),

        "total": total,
        "page": page,
        "limit": limit,

        "totalPages": total_pages,

        "hasNext": page < total_pages,
        "hasPrevious": page > 1,

        "data": result,
    }