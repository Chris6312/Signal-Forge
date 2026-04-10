import hashlib
import hmac
import logging
import time
import urllib.parse
import base64

import httpx

from app.common.config import settings
from app.common.symbols import kraken_provider_pair

logger = logging.getLogger(__name__)

KRAKEN_BASE = "https://api.kraken.com"


class KrakenClient:
    def __init__(self):
        self.api_key = settings.KRAKEN_API_KEY
        self.api_secret = settings.KRAKEN_API_SECRET

    def _sign(self, url_path: str, data: dict) -> str:
        post_data = urllib.parse.urlencode(data)
        encoded = (str(data.get("nonce", "")) + post_data).encode()
        message = url_path.encode() + hashlib.sha256(encoded).digest()
        mac = hmac.new(base64.b64decode(self.api_secret), message, hashlib.sha512)
        return base64.b64encode(mac.digest()).decode()

    async def _public(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{KRAKEN_BASE}/0/public/{endpoint}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params or {})
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(f"Kraken API error: {data['error']}")
            return data.get("result", {})

    async def _private(self, endpoint: str, payload: dict | None = None) -> dict:
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Kraken API credentials not configured")
        url_path = f"/0/private/{endpoint}"
        url = f"{KRAKEN_BASE}{url_path}"
        data = dict(payload or {})
        data["nonce"] = str(int(time.time() * 1000))
        sig = self._sign(url_path, data)
        headers = {"API-Key": self.api_key, "API-Sign": sig}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            if result.get("error"):
                raise RuntimeError(f"Kraken API error: {result['error']}")
            return result.get("result", {})

    async def get_ticker(self, pair: str) -> dict:
        try:
            provider_pair = kraken_provider_pair(pair)
        except Exception:
            provider_pair = pair
        data = await self._public("Ticker", {"pair": provider_pair})
        return data.get(provider_pair) or next(iter(data.values()), {})

    async def get_ohlcv(self, pair: str, interval: int = 60) -> list:
        try:
            provider_pair = kraken_provider_pair(pair)
        except Exception:
            provider_pair = pair
        data = await self._public("OHLC", {"pair": provider_pair, "interval": interval})
        key = provider_pair if provider_pair in data else next(
            (k for k in data if k != "last"), provider_pair
        )
        return data.get(key, [])

    async def get_balance(self) -> dict:
        return await self._private("Balance")

    async def get_open_orders(self) -> dict:
        return await self._private("OpenOrders")

    async def add_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        volume: float,
        price: float | None = None,
    ) -> dict:
        try:
            provider_pair = kraken_provider_pair(pair)
        except Exception:
            provider_pair = pair
        payload = {
            "pair": provider_pair,
            "type": side.lower(),
            "ordertype": order_type.lower(),
            "volume": str(volume),
        }
        if price is not None:
            payload["price"] = str(price)
        return await self._private("AddOrder", payload)

    async def cancel_order(self, txid: str) -> dict:
        return await self._private("CancelOrder", {"txid": txid})

    async def get_closed_orders(self) -> dict:
        return await self._private("ClosedOrders")


kraken_client = KrakenClient()
