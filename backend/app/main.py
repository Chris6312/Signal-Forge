import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.common.config import settings
from app.common.database import init_db
from app.common.runtime_state import runtime_state
from app.common.ws_manager import ws_manager
from app.api.routes import dashboard, watchlist, monitoring, positions, ledger, trades, audit, runtime, ws

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class _WorkerThread:
    """Runs a single async worker in a dedicated OS thread with its own event loop.

    Each thread gets an independent asyncio event loop, so its DB connections
    (NullPool) and Redis client (threading.local) never contend with the main
    FastAPI event loop or with each other.
    """

    def __init__(self, coro_fn: Callable[[], Coroutine], name: str) -> None:
        self._coro_fn  = coro_fn
        self.name      = name
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._task:   asyncio.Task | None              = None
        self._thread: threading.Thread | None          = None
        self._started = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=self.name, daemon=True
        )
        self._thread.start()
        self._started.wait(timeout=5.0)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._task = self._loop.create_task(self._coro_fn())
        finally:
            self._started.set()
        try:
            self._loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Worker thread '%s' crashed: %s", self.name, exc, exc_info=True)
        finally:
            self._loop.close()

    def stop(self, timeout: float = 15.0) -> None:
        if self._loop and self._task and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._task.cancel)
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "Worker thread '%s' did not stop within %s s", self.name, timeout
                )


async def heartbeat_worker():
    while True:
        try:
            await asyncio.sleep(30)
            await runtime_state.heartbeat()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Heartbeat error: %s", exc)


async def ws_broadcast_worker():
    from app.api.routes.ws import build_dashboard_payload, build_market_status_payload
    tick = 0
    while True:
        try:
            await asyncio.sleep(10)
            tick += 1
            if ws_manager._clients:
                await ws_manager.broadcast("dashboard_update", await build_dashboard_payload())
                if tick % 6 == 0:  # market status every ~60 s
                    await ws_manager.broadcast("market_status_update", build_market_status_payload())
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("WS broadcast error: %s", exc)


async def reconciliation_worker():
    while True:
        try:
            await asyncio.sleep(300)
            await _run_reconciliation()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Reconciliation error: %s", exc)


async def _run_reconciliation():
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from sqlalchemy import select, func
    from app.common.database import AsyncSessionLocal
    from app.common.models.position import Position, PositionState
    from app.common.models.ledger import LedgerAccount
    from app.crypto.ledger import crypto_ledger
    from app.stocks.ledger import stock_ledger

    now = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)
    ledger_map = {"crypto": crypto_ledger, "stock": stock_ledger}
    summaries: dict[str, float] = {}

    async with AsyncSessionLocal() as db:
        for asset_class, ledger_obj in ledger_map.items():
            stmt = select(func.sum(Position.pnl_unrealized)).where(
                Position.asset_class == asset_class,
                Position.state == PositionState.OPEN,
                Position.pnl_unrealized.isnot(None),
            )
            result = await db.execute(stmt)
            total_unrealized: float = result.scalar() or 0.0
            summaries[asset_class] = total_unrealized

            account = await ledger_obj.get_account(db)
            account.unrealized_pnl = total_unrealized
            account.last_reconciled_at = now
            account.updated_at = now

        await db.commit()

    logger.info(
        "Reconciliation complete — crypto unrealized=%.4f | stock unrealized=%.4f",
        summaries.get("crypto", 0.0),
        summaries.get("stock", 0.0),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.APP_NAME)
    await init_db()
    await runtime_state.initialize()
    ws_manager.set_main_loop(asyncio.get_running_loop())

    _worker_threads: list[_WorkerThread] = []
    _main_tasks:     list[asyncio.Task]  = []

    try:
        from app.common.discord_listener import discord_listener
        wt = _WorkerThread(discord_listener.start, "discord_listener")
        wt.start()
        _worker_threads.append(wt)
    except Exception as exc:
        logger.warning("Discord listener not started: %s", exc)

    try:
        from app.crypto.monitoring  import crypto_monitor
        from app.crypto.exit_worker import crypto_exit_worker
        from app.stocks.monitoring  import stock_monitor
        from app.stocks.exit_worker import stock_exit_worker

        for coro_fn, name in [
            (crypto_monitor.run,     "crypto_monitor"),
            (crypto_exit_worker.run, "crypto_exit_worker"),
            (stock_monitor.run,      "stock_monitor"),
            (stock_exit_worker.run,  "stock_exit_worker"),
        ]:
            wt = _WorkerThread(coro_fn, name)
            wt.start()
            _worker_threads.append(wt)
    except Exception as exc:
        logger.warning("Worker startup error: %s", exc)

    _main_tasks.extend([
        asyncio.create_task(heartbeat_worker(),      name="heartbeat"),
        asyncio.create_task(reconciliation_worker(), name="reconciliation"),
        asyncio.create_task(ws_broadcast_worker(),   name="ws_broadcast"),
    ])

    logger.info(
        "%s started with %d worker thread(s)", settings.APP_NAME, len(_worker_threads)
    )

    yield

    logger.info("Shutting down %s", settings.APP_NAME)
    await runtime_state.set_status("offline")

    for task in _main_tasks:
        task.cancel()
    await asyncio.gather(*_main_tasks, return_exceptions=True)

    for wt in _worker_threads:
        wt.stop(timeout=15.0)


app = FastAPI(
    title="Signal Forge",
    description="AI Multi-Asset Trading Bot",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "x-admin-token"],
)

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["watchlist"])
app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])
app.include_router(positions.router, prefix="/api/positions", tags=["positions"])
app.include_router(ledger.router, prefix="/api/ledger", tags=["ledger"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(runtime.router, prefix="/api/runtime", tags=["runtime"])
app.include_router(ws.router)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": "1.0.0"}
