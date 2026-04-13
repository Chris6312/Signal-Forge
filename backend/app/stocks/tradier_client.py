import logging
import httpx
from app.common.config import settings

logger = logging.getLogger(__name__)

TRADIER_BASE = "https://api.tradier.com/v1"


class TradierClient:
    def __init__(self):
        self.token = settings.TRADIER_ACCESS_TOKEN
        self.account_id = settings.TRADIER_ACCOUNT_ID
        self.base = TRADIER_BASE

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    async def get_quote(self, symbols: str | list) -> dict:
        if isinstance(symbols, list):
            symbols = ",".join(symbols)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base}/markets/quotes",
                headers=self._headers,
                params={"symbols": symbols, "greeks": "false"},
            )
            resp.raise_for_status()
            data = resp.json()
            quotes = data.get("quotes", {}).get("quote", {})
            if isinstance(quotes, dict):
                return {quotes["symbol"]: quotes}
            return {q["symbol"]: q for q in quotes}

    async def get_history(self, symbol: str, interval: str = "daily", start: str = "", end: str = "") -> list:
        params = {"symbol": symbol, "interval": interval}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base}/markets/history",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            history = data.get("history", {})
            if not history:
                return []
            days = history.get("day", [])
            return days if isinstance(days, list) else [days]

    async def get_timesales(
        self,
        symbol: str,
        interval: str = "1min",
        start: str = "",
        end: str = "",
    ) -> list:
        params: dict = {"symbol": symbol, "interval": interval, "session_filter": "open"}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base}/markets/timesales",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            series = data.get("series", {})
            if not series:
                return []
            candles = series.get("data", [])
            return candles if isinstance(candles, list) else [candles]

    async def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "market",
        price: float | None = None,
        stop: float | None = None,
        duration: str = "day",
    ) -> dict:
        if not self.token or not self.account_id:
            raise RuntimeError("Tradier credentials not configured")
        payload = {
            "class": "equity",
            "symbol": symbol,
            "side": side.lower(),
            "quantity": str(quantity),
            "type": order_type.lower(),
            "duration": duration,
        }
        if price is not None:
            payload["price"] = str(price)
        if stop is not None:
            payload["stop"] = str(stop)

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self.base}/accounts/{self.account_id}/orders",
                headers=self._headers,
                data=payload,
            )
            resp.raise_for_status()
            return resp.json().get("order", {})

    async def cancel_order(self, order_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                f"{self.base}/accounts/{self.account_id}/orders/{order_id}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json().get("order", {})

    async def get_positions(self) -> list:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base}/accounts/{self.account_id}/positions",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            positions = data.get("positions", {})
            if not positions or positions == "null":
                return []
            pos = positions.get("position", [])
            return pos if isinstance(pos, list) else [pos]

    async def get_balances(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base}/accounts/{self.account_id}/balances",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json().get("balances", {})


tradier_client = TradierClient()
