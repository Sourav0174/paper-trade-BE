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


def fetch_historical_prices(
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:
    """
    Returns OHLC history for a symbol.

    Empty DataFrame on failure or when no data is available.
    """

    try:
        stock = yf.Ticker(symbol + ".NS")

        data = stock.history(
            period=period,
            interval=interval,
        )

        if data is None or data.empty:
            return pd.DataFrame()

        return data

    except Exception:
        logger.exception(
            "Failed fetching history for %s (period=%s, interval=%s)",
            symbol,
            period,
            interval,
        )
        return pd.DataFrame()


HISTORICAL_CACHE_TTL_SECONDS = 600
MAX_HISTORICAL_CACHE_SIZE = 500

_historical_cache: Dict[
    Tuple[str, str, str],
    Tuple[float, pd.DataFrame],
] = {}

_historical_cache_lock = threading.Lock()


def get_cached_historical_prices(
    symbol: str,
    period: str,
    interval: str,
) -> pd.DataFrame:

    cache_key = (symbol, period, interval)
    now = time.time()

    with _historical_cache_lock:
        cached = _historical_cache.get(cache_key)

        if cached is not None:
            cached_at, cached_frame = cached

            if now - cached_at < HISTORICAL_CACHE_TTL_SECONDS:
                return cached_frame

    frame = fetch_historical_prices(symbol, period, interval)

    if frame.empty:
        return frame

    with _historical_cache_lock:

        expired_keys = [
            key
            for key, (cached_at, _) in _historical_cache.items()
            if now - cached_at >= HISTORICAL_CACHE_TTL_SECONDS
        ]

        for key in expired_keys:
            del _historical_cache[key]

        if len(_historical_cache) >= MAX_HISTORICAL_CACHE_SIZE:
            oldest_key = min(
                _historical_cache,
                key=lambda key: _historical_cache[key][0],
            )
            del _historical_cache[oldest_key]

        _historical_cache[cache_key] = (
            now,
            frame,
        )

    return frame

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

def extract_ticker_dataframe(tickers: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Extracts and normalizes a 2D DataFrame for a specific symbol from yfinance output.
    Handles MultiIndex (ticker in level 0 or level 1) and single-level Index layouts.
    """
    if tickers is None or tickers.empty:
        return pd.DataFrame()

    ticker = f"{symbol}.NS"
    target_upper = ticker.upper()
    symbol_upper = symbol.upper()

    if isinstance(tickers.columns, pd.MultiIndex):
        l0_str = [str(x).upper() for x in tickers.columns.get_level_values(0)]
        l1_str = [str(x).upper() for x in tickers.columns.get_level_values(1)]

        # Check if ticker matches in level 0
        for orig, val in zip(tickers.columns.get_level_values(0), l0_str):
            if val in (target_upper, symbol_upper):
                sub = tickers[orig]
                return sub if isinstance(sub, pd.DataFrame) else sub.to_frame()

        # Check if ticker matches in level 1
        for orig, val in zip(tickers.columns.get_level_values(1), l1_str):
            if val in (target_upper, symbol_upper):
                sub = tickers.xs(orig, axis=1, level=1)
                return sub if isinstance(sub, pd.DataFrame) else sub.to_frame()

    # Single-level index or non-MultiIndex
    if "Close" in tickers.columns or "close" in tickers.columns:
        return tickers

    # Fallback for tuple columns or prefix string columns
    renamed = {}
    for c in tickers.columns:
        c_str = str(c)
        if ("Close" in c_str or "close" in c_str) and (symbol_upper in c_str.upper()):
            renamed[c] = "Close"
        elif ("Open" in c_str or "open" in c_str) and (symbol_upper in c_str.upper()):
            renamed[c] = "Open"
    if renamed:
        return tickers.rename(columns=renamed)

    return pd.DataFrame()


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
            return {symbol: (0.0, 0.0, 0.0) for symbol in symbols}

    except Exception as e:
        logger.exception("DOWNLOAD FAILED: %s", e)
        return {symbol: (0.0, 0.0, 0.0) for symbol in symbols}

    result: Dict[str, Tuple[float, float, float]] = {}

    for symbol in symbols:
        try:
            data = extract_ticker_dataframe(tickers, symbol)
            if data.empty or "Close" not in data.columns:
                raise ValueError(f"No Close price data for {symbol}")

            close_col = data["Close"]
            if isinstance(close_col, pd.DataFrame):
                close_col = close_col.iloc[:, 0]

            close_series = close_col.dropna()
            if close_series.empty:
                raise ValueError(f"Empty Close series for {symbol}")

            current_price = round(safe_float(close_series.iloc[-1]), 2)

            if len(close_series) >= 2:
                previous_close = round(
                    safe_float(close_series.iloc[-2], current_price),
                    2,
                )
            else:
                previous_close = current_price

            change_value = round(current_price - previous_close, 2)

            if previous_close == 0:
                change_percent = 0.0
            else:
                change_percent = round(
                    ((current_price - previous_close) / previous_close) * 100,
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
            result[symbol] = (0.0, 0.0, 0.0)

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