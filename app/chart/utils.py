from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Optional


SYMBOL_MAP: Dict[str, str] = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
}


@dataclass(frozen=True)
class TimeframeConfig:
    """Candle granularity and yfinance fetch constraints for a chart timeframe."""

    interval: str
    bar_seconds: int
    max_lookback: Optional[timedelta]
    overfetch_multiplier: float


# yfinance enforces provider-side lookback caps on intraday intervals
# (~60 days for sub-hourly, ~730 days for hourly); daily+ intervals have
# no such cap. `max_lookback` encodes that boundary so pagination can
# stop requesting once it's reached instead of erroring against yfinance.
#
# `overfetch_multiplier` accounts for non-trading time (nights, weekends,
# holidays) that a naive `limit * bar_seconds` window wouldn't cover:
# ~6x for intraday bars (NSE trades ~6h15m of each 24h, 5 of 7 days),
# ~1.6x for daily+ bars (5 of 7 calendar days, plus a holiday buffer).
TIMEFRAME_MAP: Dict[str, TimeframeConfig] = {
    "1D": TimeframeConfig("5m", 300, timedelta(days=59), 6.0),
    "1W": TimeframeConfig("15m", 900, timedelta(days=59), 6.0),
    "1M": TimeframeConfig("1h", 3600, timedelta(days=729), 6.0),
    "3M": TimeframeConfig("1d", 86400, None, 1.6),
    "1Y": TimeframeConfig("1d", 86400, None, 1.6),
}
