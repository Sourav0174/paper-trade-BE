import os
import time
import httpx


class MarketService:
    def __init__(self):
        self.cache = []
        self.last_fetched = 0
        self.cache_duration = 60

        self.api_key = os.getenv("TWELVE_DATA_API_KEY")

    async def fetch_market_indexes(self):
        symbols = {
            "NIFTY 50": "NIFTYBEES",
            "BANK NIFTY": "BANKBEES",
        }

        formatted = []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:

                for display_name, symbol in symbols.items():

                    response = await client.get(
                        "https://api.twelvedata.com/quote",
                        params={
                            "symbol": symbol,
                            "exchange": "NSE",
                            "apikey": self.api_key,
                        },
                    )

                    print(
                        f"{symbol}:",
                        response.status_code,
                        response.text[:300],
                    )

                    if response.status_code != 200:
                        continue

                    data = response.json()

                    if data.get("status") == "error":
                        print("TwelveData Error:", data)
                        continue

                    try:
                        price = float(data.get("close", 0))
                        change_percent = float(
                            data.get("percent_change", 0)
                        )
                    except Exception:
                        continue

                    formatted.append({
                        "name": display_name,
                        "value": price,
                        "changePercent": change_percent,
                        "isUp": change_percent >= 0,
                    })

            return formatted

        except Exception as e:
            print("MarketService Error:", e)
            return self.cache

    async def get_indexes(self):
        current_time = time.time()

        if (
            current_time - self.last_fetched
            < self.cache_duration
        ):
            return self.cache

        data = await self.fetch_market_indexes()

        self.cache = data
        self.last_fetched = current_time

        return data


market_service = MarketService()