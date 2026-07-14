import logging
import math
import threading
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple
import pandas as pd
import yfinance as yf
import json
from pathlib import Path

DATA_PATH = (
    Path(__file__).parent
    / "data"
    / "nse_stocks.json"
)

with open(DATA_PATH, "r", encoding="utf-8") as f:
    ALL_STOCKS = json.load(f)

logger = logging.getLogger(__name__)


def get_market_status() -> str:

    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))

    # Monday = 0 ... Sunday = 6
    if now_ist.weekday() >= 5:
        return "CLOSED"

    market_open = dtime(9, 15)
    market_close = dtime(15, 30)

    if market_open <= now_ist.time() <= market_close:
        return "OPEN"

    return "CLOSED"

def safe_float(value, default=0.0):
    """
    Converts any value to float while protecting against:
    - None
    - NaN
    - Infinity
    """

    try:
        value = float(value)

        if math.isnan(value) or math.isinf(value):
            return default

        return value

    except Exception:
        return default


def fetch_single_price(symbol: str):
    price, _ = fetch_real_price(symbol)
    logger.debug("Fetched price for %s: %s", symbol, price)

    if price <= 0:
        return None

    return round(float(price), 2)

def fetch_real_price(symbol: str):
    try:
        stock = yf.Ticker(symbol + ".NS")

        data = stock.history(period="5d")

        if data.empty:
            return 0.0, 0.0

        value = safe_float(data["Close"].iloc[-1])

        open_price = safe_float(
            data["Open"].iloc[-1],
            value,
        )

        if open_price == 0:
            change = 0.0
        else:
            change = round(
                ((value - open_price) / open_price) * 100,
                2,
            )

        return round(value, 2), change

    except Exception:
        logger.exception("Failed fetching %s", symbol)
        return 0.0, 0.0

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
            tickers=" ".join(f"{s}.NS" for s in symbols),
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
        logger.exception("DOWNLOAD FAILED: %s", e)

        return {
            symbol: (0.0, 0.0, 0.0)
            for symbol in symbols
        }

    result: Dict[str, Tuple[float, float, float]] = {}

    for symbol in symbols:

        try:

            if len(symbols) == 1:
                data = tickers

            else:
                if isinstance(
                    tickers.columns,
                    pd.MultiIndex,
                ):
                    data = tickers[f"{symbol}.NS"]
                else:
                    data = tickers

            if data.empty:
                raise ValueError("No data")

            current_price = round(
                safe_float(data["Close"].iloc[-1]),
                2,
            )

            if len(data) >= 2:
                previous_close = round(
                    safe_float(
                        data["Close"].iloc[-2],
                        current_price,
                    ),
                    2,
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
                    ((current_price - previous_close) / previous_close)
                    * 100,
                    2,
                )

            change_percent = safe_float(change_percent)

            result[symbol] = (
                current_price,
                change_value,
                change_percent,
            )

        except Exception:
            logger.exception("Failed to process price data for %s", symbol)

            result[symbol] = (
                0.0,
                0.0,
                0.0,
            )

    return result


# ---------------------------------
# In-memory price cache (60s TTL)
# ---------------------------------

CACHE_TTL_SECONDS = 60

_price_cache: Dict[Tuple[str, ...], Tuple[float, Dict[str, Tuple[float, float, float]]]] = {}
_price_cache_lock = threading.Lock()


def get_cached_prices(
    symbols: List[str],
) -> Dict[str, Tuple[float, float, float]]:

    if not symbols:
        return {}

    cache_key = tuple(sorted(symbols))
    now = time.time()

    with _price_cache_lock:
        cached = _price_cache.get(cache_key)

        if cached is not None:
            cached_at, cached_prices = cached

            if now - cached_at < CACHE_TTL_SECONDS:
                return cached_prices

    fresh_prices = fetch_multiple_prices(symbols)

    with _price_cache_lock:
        # Remove expired cache entries
        expired_keys = [
            key
            for key, (cached_at, _) in _price_cache.items()
            if now - cached_at >= CACHE_TTL_SECONDS
        ]

        for key in expired_keys:
            del _price_cache[key]

        # Save new cache
        _price_cache[cache_key] = (
            now,
            fresh_prices,
        )

    return fresh_prices

def get_stocks(
    page: int,
    limit: int,
    search: str | None = None,
):
    """
    Fetch all NSE stocks with
    - Search
    - Pagination
    - Real-time prices (cached for 60s)
    """

    # ---------------------------------
    # Use all NSE stocks
    # ---------------------------------

    stocks = ALL_STOCKS.copy()

    # ---------------------------------
    # Search
    # ---------------------------------

    if search:
        keyword = search.strip().lower()

        stocks = [
            stock
            for stock in stocks
            if keyword in stock["symbol"].lower()
            or keyword in stock["name"].lower()
        ]

    # ---------------------------------
    # Sort alphabetically
    # ---------------------------------

    stocks.sort(key=lambda x: x["symbol"])

    # ---------------------------------
    # Pagination FIRST
    # ---------------------------------

    total = len(stocks)

    total_pages = max(
        (total + limit - 1) // limit,
        1,
    )

    start = (page - 1) * limit
    end = start + limit

    # Slicing beyond the list bounds naturally yields an empty list
    # (no exception), so out-of-range pages simply return no data
    # while total/totalPages/hasNext/hasPrevious stay accurate.
    paginated = stocks[start:end]

    # ---------------------------------
    # Fetch prices ONLY for current page (cached)
    # ---------------------------------

    symbols = [
        stock["symbol"]
        for stock in paginated
    ]

    price_map = get_cached_prices(symbols)

    stock_list = []

    for stock in paginated:

        current_price, change_value, change_percent = price_map.get(
            stock["symbol"],
            (0.0, 0.0, 0.0),
        )

        stock_list.append(
            {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "exchange": "NSE",
                "currentPrice": safe_float(current_price),
                "changeValue": safe_float(change_value),
                "changePercent": safe_float(change_percent),
                "isUp": safe_float(change_percent) >= 0,
            }
        )

    # ---------------------------------
    # Response
    # ---------------------------------

    return {
        "marketStatus": get_market_status(),
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages,
        "hasNext": page < total_pages,
        "hasPrevious": page > 1,
        "data": stock_list,
    }