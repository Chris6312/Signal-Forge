import asyncio
import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.common.watchlist_engine import watchlist_engine
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.database import AsyncSessionLocal


def test_process_update_adds_and_updates(monkeypatch):
    # Prepare a fake DB session and behaviour
    fake_db = AsyncMock()
    # existing query should return no existing rows
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []
    fake_db.execute = AsyncMock(return_value=fake_result)
    # db.add should be a normal callable (watchlist_engine calls db.add() without awaiting)
    fake_db.add = lambda obj: None
    fake_db.commit = AsyncMock()

    class _Ctx:
        def __init__(self, db):
            self._db = db

        async def __aenter__(self):
            return self._db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('app.common.watchlist_engine.AsyncSessionLocal', lambda: _Ctx(fake_db))

    payload = [
        {"symbol": "BTCUSD", "asset_class": "crypto", "reason": "momentum", "confidence": 0.87, "tags": ["btc","momentum"]},
        {"symbol": "AAPL", "asset_class": "stock", "reason": "earnings", "confidence": 0.65},
    ]

    import asyncio
    result = asyncio.run(watchlist_engine.process_update(payload, source_id='unittest', payload_meta=None))

    assert result['total'] == 2
    # canonical_symbol will normalize BTCUSD to BTC/USD; accept either form
    assert any(x in ('BTCUSD', 'BTC/USD') for x in result['added'])
    assert 'AAPL' in result['added']


def test_process_update_skips_invalid_asset_class(monkeypatch):
    fake_db = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []
    fake_db.execute = AsyncMock(return_value=fake_result)
    fake_db.add = lambda obj: None
    fake_db.commit = AsyncMock()

    class _Ctx:
        def __init__(self, db):
            self._db = db

        async def __aenter__(self):
            return self._db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('app.common.watchlist_engine.AsyncSessionLocal', lambda: _Ctx(fake_db))

    payload = [
        {"symbol": "FOO", "asset_class": "derivative"},
        {"symbol": "BAR", "asset_class": ""},
    ]

    import asyncio
    result = asyncio.run(watchlist_engine.process_update(payload, source_id='unittest', payload_meta=None))


def test_process_update_v4_validation_and_ai_hint(monkeypatch):
    fake_db = AsyncMock()
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []
    fake_db.execute = AsyncMock(return_value=fake_result)
    fake_db.add = lambda obj: None
    fake_db.commit = AsyncMock()

    class _Ctx:
        def __init__(self, db):
            self._db = db

        async def __aenter__(self):
            return self._db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('app.common.watchlist_engine.AsyncSessionLocal', lambda: _Ctx(fake_db))

    payload = [
        {"symbol": "BTC/USD", "asset_class": "crypto", "ai_hint": {"suggested_strategy": "trend_continuation", "confidence": 0.85}},
        {"symbol": "INVALID", "asset_class": "crypto", "ai_hint": {"suggested_strategy": "unknown_strategy", "confidence": 0.5}},
    ]

    meta = {"schema_version": "bot_watchlist_v4", "timestamp": datetime.now(timezone.utc).isoformat()}
    result = asyncio.run(watchlist_engine.process_update(payload, source_id='unittest', payload_meta=meta))
    # One valid (BTC/USD) added, one invalid skipped
    assert result['total'] == 1


def test_process_update_promotes_managed_symbol_and_clears_closed_at(monkeypatch):
    watchlist_symbol = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        symbol="AAPL",
        asset_class="stock",
        state=SymbolState.MANAGED,
        watchlist_source_id="old-source",
        notes="old notes",
        reason="old reason",
        confidence=0.5,
        tags=["old"],
        added_at=datetime(2026, 1, 1, 10, 0, 0),
        removed_at=datetime(2026, 1, 2, 10, 0, 0),
        managed_since=datetime(2026, 1, 2, 10, 0, 0),
        closed_at=datetime(2026, 1, 3, 10, 0, 0),
    )

    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [watchlist_symbol]

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=fake_result)
    fake_db.add = lambda obj: None
    fake_db.commit = AsyncMock()

    class _Ctx:
        def __init__(self, db):
            self._db = db

        async def __aenter__(self):
            return self._db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr('app.common.watchlist_engine.AsyncSessionLocal', lambda: _Ctx(fake_db))

    result = asyncio.run(
        watchlist_engine.process_update(
            [{"symbol": "AAPL", "asset_class": "stock", "reason": "updated", "confidence": 0.9, "tags": ["new"], "notes": "fresh"}],
            source_id='unittest',
            payload_meta=None,
        )
    )

    assert result['promoted'] == ['AAPL']
    assert watchlist_symbol.state is SymbolState.ACTIVE
    assert watchlist_symbol.watchlist_source_id == 'unittest'
    assert watchlist_symbol.removed_at is None
    assert watchlist_symbol.managed_since is None
    assert watchlist_symbol.closed_at is None
    assert watchlist_symbol.reason == 'updated'
    assert watchlist_symbol.confidence == pytest.approx(0.9)
    assert watchlist_symbol.tags == ['new']
    assert watchlist_symbol.notes == 'fresh'

