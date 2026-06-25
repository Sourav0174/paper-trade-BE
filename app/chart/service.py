import yfinance as yf

from fastapi import HTTPException

from app.chart.utils import SYMBOL_MAP, TIMEFRAME_MAP


class ChartService:

    async def get_chart_data(
        self,
        symbol: str,
        timeframe: str,
    ):
        
        

        # Convert frontend symbol to provider symbol
        provider_symbol = SYMBOL_MAP.get(symbol.upper(), symbol)

        # Get timeframe config
        config = TIMEFRAME_MAP.get(timeframe)

        if not config:
            raise HTTPException(
                status_code=400,
                detail="Invalid timeframe"
            )

        try:
            ticker = yf.Ticker(provider_symbol)

            df = ticker.history(
                period=config["period"],
                interval=config["interval"]
            )

            if df.empty:
                raise HTTPException(
                    status_code=404,
                    detail="No chart data found"
                )

            candles = []

            for index, row in df.iterrows():

                candles.append({
                    "time": int(index.timestamp()), # type: ignore
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                })

            candles = candles[-300:]

            if len(candles) >= 2:
                latest = candles[-1]
                previous = candles[-2]

                ltp = round(latest["close"], 2)

                change = round(
                    latest["close"] - previous["close"],
                    2,
                )

                change_percent = (
                    round((change / previous["close"]) * 100, 2)
                    if previous["close"] > 0
                    else 0
                )
            else:
                ltp = candles[-1]["close"] if candles else 0
                change = 0
                change_percent = 0

            return {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "ltp": ltp,
                "change": change,
                "change_percent": change_percent,
                "candles": candles,
            }
        except HTTPException:
            raise

        except Exception as e:
            print("Chart Fetch Error:", e)

            raise HTTPException(
                status_code=500,
                detail="Failed to fetch chart data"
            )
        
    def get_provider_symbol(self, symbol: str):

        symbol = symbol.upper()

        if symbol in SYMBOL_MAP:
            return SYMBOL_MAP[symbol]

        if not symbol.endswith(".NS"):
            return f"{symbol}.NS"

        return symbol
        
    async def get_live_price(self, symbol: str):

        provider_symbol = self.get_provider_symbol(symbol)

        try:

            ticker = yf.Ticker(provider_symbol)

            df = ticker.history(
                period="1d",
                interval="5m",
            )

            if df.empty:
                return None

            return round(
                float(df["Close"].iloc[-1]),
                2,
            )

        except Exception as e:
            print("Live Price Error:", e)
            return None
chart_service = ChartService()