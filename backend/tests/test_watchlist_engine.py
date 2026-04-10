import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.common.watchlist_engine import watchlist_engine
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_process_update_adds_and_updates(monkeypatch):
    # Prepare a fake DB session and behaviour
    fake_db = AsyncMock()
    # existing query should return no existing rows
    fake_db.execute.return_value.scalars.return_value.all.return_value = []

    async def fake_session_context():
        yield fake_db

    monkeypatch.setattr('app.common.watchlist_engine.AsyncSessionLocal', lambda: fake_session_context())

    payload = [
        {"symbol": "BTCUSD", "asset_class": "crypto", "reason": "momentum", "confidence": 0.87, "tags": ["btc","momentum"]},
        {"symbol": "AAPL", "asset_class": "stock", "reason": "earnings", "confidence": 0.65},
    ]

    result = await watchlist_engine.process_update(payload, source_id='unittest')

    assert result['total'] == 2
    assert 'BTCUSD' in result['added']
    assert 'AAPL' in result['added']


@pytest.mark.asyncio
async def test_process_update_skips_invalid_asset_class(monkeypatch):
    fake_db = AsyncMock()
    fake_db.execute.return_value.scalars.return_value.all.return_value = []

    async def fake_session_context():
        yield fake_db

    monkeypatch.setattr('app.common.watchlist_engine.AsyncSessionLocal', lambda: fake_session_context())

    payload = [
        {"symbol": "FOO", "asset_class": "derivative"},
        {"symbol": "BAR", "asset_class": ""},
    ]

    result = await watchlist_engine.process_update(payload, source_id='unittest')
    assert result['total'] == 0

