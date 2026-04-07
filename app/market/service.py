import time
import httpx




class MarketService:
    def __init__(self):
        self.cache = []
        self.last_fetched = 0
        self.cache_duration = 10  # seconds


    async def fetch_from_nse(self):
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/",
        }

        try:
            async with httpx.AsyncClient(timeout=5.0, headers=headers) as client:
                # Step 1: Get cookies
                await client.get("https://www.nseindia.com")

                # Step 2: Fetch NIFTY 50
                nifty_response = await client.get(
                    "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
                )

                # Step 3: Fetch NIFTY BANK
                bank_response = await client.get(
                    "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20BANK"
                )

            if nifty_response.status_code != 200 or bank_response.status_code != 200:
                print("NSE API Error")
                return self.cache

            nifty_json = nifty_response.json()
            bank_json = bank_response.json()

            # IMPORTANT: data is a list
            nifty_data = nifty_json.get("data", [])
            bank_data = bank_json.get("data", [])

            formatted = []

            if nifty_data:
                nifty_item = nifty_data[0]
                percent_change = float(nifty_item.get("pChange", 0))

                formatted.append({
                    "name": "NIFTY 50",
                    "value": float(nifty_item.get("lastPrice", 0)),
                    "changePercent": percent_change,
                    "isUp": percent_change >= 0
                })

            if bank_data:
                bank_item = bank_data[0]
                percent_change = float(bank_item.get("pChange", 0))

                formatted.append({
                    "name": "NIFTY BANK",
                    "value": float(bank_item.get("lastPrice", 0)),
                    "changePercent": percent_change,
                    "isUp": percent_change >= 0
                })

            return formatted

        except Exception as e:
            print("NSE Fetch Failed:", e)
            return self.cache
    async def fetch_from_yahoo(self):
        url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=^NSEI,^NSEBANK"

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)

            if response.status_code != 200:
                print("Yahoo API Error:", response.status_code)
                return self.cache  # fallback to old cache

            try:
                data = response.json()
            except Exception:
                print("Invalid JSON from Yahoo")
                return self.cache

            formatted = []

            results = data.get("quoteResponse", {}).get("result", [])

            for item in results:
                percent_change = item.get("regularMarketChangePercent", 0)

                formatted.append({
                    "name": item.get("shortName"),
                    "value": item.get("regularMarketPrice"),
                    "changePercent": percent_change,
                    "isUp": percent_change >= 0
                })

            return formatted

        except Exception as e:
            print("Yahoo Fetch Failed:", e)
            return self.cache

    async def get_indexes(self):
        current_time = time.time()

        # Return cached data if within 10 seconds
        if current_time - self.last_fetched < self.cache_duration:
            return self.cache

        data = await self.fetch_from_nse()

        self.cache = data
        self.last_fetched = current_time

        return data


market_service = MarketService()

