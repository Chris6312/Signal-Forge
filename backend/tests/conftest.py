"""Shared fixtures and OHLCV / history builder helpers."""
import math

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.deps import get_db_session
from app.common.position_time import PositionHoldMetrics


# ---------------------------------------------------------------------------
# Crypto OHLCV helpers  [ts, open, high, low, close, volume]
# ---------------------------------------------------------------------------

def make_candle(ts: int, close: float, spread: float = 0.01) -> list:
    return [ts, close, close * (1 + spread), close * (1 - spread), close, 1000.0]


def trending_up_ohlcv(n: int = 65, start: float = 100.0, end: float = 200.0) -> list:
    """n candles with linearly increasing closes."""
    return [make_candle(i, start + (end - start) * i / max(n - 1, 1)) for i in range(n)]


def trending_down_ohlcv(n: int = 65, start: float = 200.0, end: float = 100.0) -> list:
    """n candles with linearly decreasing closes."""
    return [make_candle(i, start + (end - start) * i / max(n - 1, 1)) for i in range(n)]


def ranging_ohlcv(n: int = 65, center: float = 100.0, amplitude: float = 2.0) -> list:
    """n candles oscillating around center."""
    return [make_candle(i, center + amplitude * math.sin(i * 0.5)) for i in range(n)]


# ---------------------------------------------------------------------------
# Stock history helpers  {"open", "high", "low", "close", "volume"}
# ---------------------------------------------------------------------------

def make_bar(close: float, spread: float = 0.01) -> dict:
    return {
        "open": close,
        "high": close * (1 + spread),
        "low": close * (1 - spread),
        "close": close,
        "volume": 1000,
    }


def trending_up_history(n: int = 65, start: float = 100.0, end: float = 200.0) -> list:
    return [make_bar(start + (end - start) * i / max(n - 1, 1)) for i in range(n)]


def trending_down_history(n: int = 65, start: float = 200.0, end: float = 100.0) -> list:
    return [make_bar(start + (end - start) * i / max(n - 1, 1)) for i in range(n)]


def ranging_history(n: int = 65, center: float = 100.0, amplitude: float = 2.0) -> list:
    return [make_bar(center + amplitude * math.sin(i * 0.5)) for i in range(n)]


def make_hold_metrics(hours_held: float, max_hold_hours: int | float | None, hold_ratio: float | None, time_risk_state: str | None) -> PositionHoldMetrics:
    return PositionHoldMetrics(
        hours_held=hours_held,
        max_hold_hours=max_hold_hours,
        hold_ratio=hold_ratio,
        time_risk_state=time_risk_state,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Async mock SQLAlchemy session wired with empty-result defaults."""
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=result)
    return db, result


@pytest.fixture
def api_client(mock_db):
    """TestClient with the DB dependency overridden by a mock session.

    The lifespan (DB engine, Redis) is intentionally NOT triggered because
    we instantiate TestClient without the context manager.
    """
    db, _ = mock_db

    async def _override():
        yield db

    app.dependency_overrides[get_db_session] = _override
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()
