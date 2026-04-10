import logging
import threading
from typing import Optional

import redis.asyncio as aioredis
from app.common.config import settings

logger = logging.getLogger(__name__)

# One connection pool per OS thread, each bound to that thread's own event loop.
_thread_local = threading.local()


async def get_redis() -> aioredis.Redis:
    """Return a thread-local Redis client, creating it if necessary.

    The function validates the REDIS_URL and logs the creation. Callers
    should not rely on the object persisting across different OS threads.
    """
    client: Optional[aioredis.Redis] = getattr(_thread_local, "client", None)
    if client is None:
        try:
            client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
            )
            _thread_local.client = client
            logger.debug("Created new Redis client for thread %s", threading.get_ident())
        except Exception as exc:
            logger.error("Failed to create Redis client: %s", exc)
            raise
    return client


async def close_redis() -> None:
    """Close and clear the thread-local Redis client if present."""
    client: Optional[aioredis.Redis] = getattr(_thread_local, "client", None)
    if client:
        try:
            await client.aclose()
        except Exception as exc:
            logger.warning("Error closing Redis client: %s", exc)
        finally:
            _thread_local.client = None
            logger.debug("Closed Redis client for thread %s", threading.get_ident())
