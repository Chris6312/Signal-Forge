import logging
import threading
import redis.asyncio as aioredis
from app.common.config import settings

logger = logging.getLogger(__name__)

# One connection pool per OS thread, each bound to that thread's own event loop.
_thread_local = threading.local()


async def get_redis() -> aioredis.Redis:
    client = getattr(_thread_local, "client", None)
    if client is None:
        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        _thread_local.client = client
    return client


async def close_redis():
    client = getattr(_thread_local, "client", None)
    if client:
        await client.aclose()
        _thread_local.client = None
