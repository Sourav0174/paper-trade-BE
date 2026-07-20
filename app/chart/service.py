import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pandas as pd
import yfinance as yf

from fastapi import HTTPException

from app.chart.utils import SYMBOL_MAP, TIMEFRAME_MAP, TimeframeConfig

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 300
MAX_LIMIT = 1000

# Bounds how many times a single page fetch will widen its request window
# and retry before giving up. Keeps worst-case yfinance calls bounded
# instead of ever falling back to "just download everything".
MAX_WINDOW_EXPANSIONS = 3


@dataclass(frozen=True)
class CandlePage:
    candles: List[dict]
    has_more: bool


class ChartService:

    # ------------------------------------------------------------------
    # Symbol / timeframe / cursor resolution
    # ------------------------------------------------------------------

    def get_provider_symbol(self, symbol: str) -> str:
        symbol = symbol.upper()

        if symbol in SYMBOL_MAP:
            return SYMBOL_MAP[symbol]

        if not symbol.endswith((".NS", ".BO")):
            return f"{symbol}.NS"

        return symbol

    def _resolve_timeframe(self, timeframe: str) -> TimeframeConfig:
        config = TIMEFRAME_MAP.get(timeframe)

        if config is None:
            raise HTTPException(status_code=400, detail="Invalid timeframe")

        return config

    def _parse_before(self, before: Optional[int]) -> Optional[datetime]:
        if before is None:
            return None

        if before < 0:
            raise HTTPException(status_code=400, detail="Invalid 'before' timestamp")

        try:
            cursor = datetime.fromtimestamp(before, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid 'before' timestamp")

        if cursor > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise HTTPException(
                status_code=400,
                detail="'before' cannot be in the future",
            )

        return cursor

    # ------------------------------------------------------------------
    # History window calculation
    # ------------------------------------------------------------------

    def _earliest_allowed(self, config: TimeframeConfig) -> Optional[datetime]:
        if config.max_lookback is None:
            return None

        return datetime.now(timezone.utc) - config.max_lookback

    def _compute_window(
        self,
        config: TimeframeConfig,
        end: datetime,
        limit: int,
        multiplier: float,
    ) -> Tuple[datetime, bool]:
        """Returns (start, clamped) for a single fetch attempt."""

        span = timedelta(seconds=config.bar_seconds * limit * multiplier)
        start = end - span

        earliest_allowed = self._earliest_allowed(config)
        clamped = False

        if earliest_allowed is not None and start < earliest_allowed:
            start = earliest_allowed
            clamped = True

        return start, clamped

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _fetch_history(
        self,
        provider_symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> pd.DataFrame:
        """Blocking yfinance call — always invoke via asyncio.to_thread."""

        ticker = yf.Ticker(provider_symbol)

        return ticker.history(
            start=start,
            end=end,
            interval=interval,
        )

    async def _safe_fetch_history(
        self,
        provider_symbol: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> pd.DataFrame:
        try:
            return await asyncio.to_thread(
                self._fetch_history,
                provider_symbol,
                start,
                end,
                interval,
            )
        except Exception:
            logger.exception(
                "yfinance history fetch failed for %s (%s -> %s, interval=%s)",
                provider_symbol,
                start,
                end,
                interval,
            )
            raise HTTPException(
                status_code=502,
                detail="Failed to fetch chart data from upstream provider",
            )

    def _format_candles(
        self,
        frame: pd.DataFrame,
        before: Optional[datetime] = None,
    ) -> List[dict]:
        if frame is None or frame.empty:
            return []

        frame = frame.dropna(subset=["Open", "High", "Low", "Close"])

        if frame.empty:
            return []

        if isinstance(frame.index, pd.DatetimeIndex) and frame.index.tz is None: # type: ignore
            # yfinance normally returns a tz-aware index. Fall back to UTC
            # if a provider response ever comes back naive, so `.timestamp()`
            # doesn't silently assume server-local time and `index < before`
            # doesn't raise on a tz-aware/tz-naive comparison.
            frame = frame.tz_localize(timezone.utc)

        frame = frame.sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]

        return [
            {
                "time": int(index.timestamp()),  # type: ignore
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
            }
            for index, row in frame.iterrows()
            if before is None or index < before  # type: ignore
        ]

    async def _fetch_page(
        self,
        provider_symbol: str,
        config: TimeframeConfig,
        end: datetime,
        limit: int,
    ) -> CandlePage:
        """
        Fetches up to `limit` candles strictly before `end`. If the first
        attempt doesn't cover enough calendar time to yield `limit` bars
        (e.g. sparse trading, holidays), the window is widened and retried
        up to MAX_WINDOW_EXPANSIONS times, capped by the timeframe's
        provider lookback limit.
        """

        multiplier = config.overfetch_multiplier
        candles: List[dict] = []
        clamped = False

        for _ in range(MAX_WINDOW_EXPANSIONS):
            start, clamped = self._compute_window(config, end, limit, multiplier)

            frame = await self._safe_fetch_history(
                provider_symbol, start, end, config.interval,
            )
            candles = self._format_candles(frame, before=end)

            if len(candles) >= limit or clamped:
                break

            multiplier *= 2

        if len(candles) > limit:
            # More candles were fetched than requested — the discarded
            # older ones prove there's more, even if this fetch was clamped.
            has_more = True
        elif len(candles) == limit:
            # Filled exactly one page. If the fetch wasn't clamped we can't
            # tell whether more history exists without another request, so
            # assume yes; the next page returning empty is what stops the
            # client. If it was clamped, start == the provider's lookback
            # boundary, so there is nothing earlier to find.
            has_more = not clamped
        else:
            has_more = False

        return CandlePage(candles=candles[-limit:], has_more=has_more)

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def _compute_quote(
        self,
        candles: List[dict],
    ) -> Tuple[float, float, float]:
        latest = candles[-1]
        ltp = round(latest["close"], 2)

        if len(candles) < 2:
            return ltp, 0.0, 0.0

        previous = candles[-2]
        change = round(latest["close"] - previous["close"], 2)

        change_percent = (
            round((change / previous["close"]) * 100, 2)
            if previous["close"] > 0
            else 0.0
        )

        return ltp, change, change_percent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_chart_data(
        self,
        symbol: str,
        timeframe: str,
        limit: int = DEFAULT_LIMIT,
        before: Optional[int] = None,
    ) -> dict:

        if not symbol or not symbol.strip():
            raise HTTPException(status_code=400, detail="Symbol is required")

        limit = max(1, min(limit, MAX_LIMIT))

        config = self._resolve_timeframe(timeframe)
        cursor = self._parse_before(before)
        provider_symbol = self.get_provider_symbol(symbol)
        end = cursor or datetime.now(timezone.utc)

        page = await self._fetch_page(provider_symbol, config, end, limit)

        if not page.candles and cursor is None:
            raise HTTPException(
                status_code=404,
                detail=f"No chart data found for '{symbol.upper()}'",
            )

        ltp = change = change_percent = None

        if cursor is None and page.candles:
            ltp, change, change_percent = self._compute_quote(page.candles)

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "ltp": ltp,
            "change": change,
            "change_percent": change_percent,
            "candles": page.candles,
            "has_more": page.has_more,
        }

    async def get_live_price(self, symbol: str) -> Optional[float]:
        provider_symbol = self.get_provider_symbol(symbol)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=2)

        try:
            frame = await self._safe_fetch_history(provider_symbol, start, end, "5m")
        except HTTPException:
            return None

        candles = self._format_candles(frame)

        return candles[-1]["close"] if candles else None


chart_service = ChartService()
