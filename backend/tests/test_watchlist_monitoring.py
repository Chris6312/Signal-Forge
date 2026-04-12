"""Tests for watchlist monitoring paths."""

from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.common.models.watchlist import SymbolState
from app.common.watchlist_engine import watchlist_engine


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "has_open_position,expected_state,expected_removed_suffix",
    [
        (True, SymbolState.MANAGED, "MANAGED"),
        (False, SymbolState.INACTIVE, "INACTIVE"),
    ],
)
async def test_process_update_preserves_managed_lifecycle_for_removed_symbol(monkeypatch, has_open_position, expected_state, expected_removed_suffix):
    watchlist_symbol = SimpleNamespace(symbol="AAPL", asset_class="stock", state=SymbolState.ACTIVE, managed_since=None, removed_at=None)

    existing_result = MagicMock()
    existing_result.scalars.return_value.all.return_value = [watchlist_symbol]

    open_result = MagicMock()
    open_result.__iter__.return_value = iter([SimpleNamespace(symbol="AAPL", asset_class="stock")]) if has_open_position else iter([])

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=[existing_result, open_result])
    fake_db.add = lambda obj: None
    fake_db.commit = AsyncMock()

    class _Ctx:
        def __init__(self, db):
            self._db = db

        async def __aenter__(self):
            return self._db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.common.watchlist_engine.AsyncSessionLocal", lambda: _Ctx(fake_db))

    result = await watchlist_engine.process_update([], source_id="unit-test", payload_meta=None)

    assert result["removed"] == [f"AAPL -> {expected_removed_suffix}"]
    assert watchlist_symbol.state is expected_state
    if has_open_position:
        assert watchlist_symbol.managed_since is not None
        assert watchlist_symbol.removed_at is None
    else:
        assert watchlist_symbol.removed_at is not None
        assert watchlist_symbol.managed_since is None
