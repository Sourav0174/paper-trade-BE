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

          
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": candles[-300:]
            }

        except HTTPException:
            raise

        except Exception as e:
            print("Chart Fetch Error:", e)

            raise HTTPException(
                status_code=500,
                detail="Failed to fetch chart data"
            )


chart_service = ChartService()