from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.crypto.monitoring import CryptoMonitor


@pytest.mark.asyncio
async def test_crypto_monitor_skips_zero_sized_execution(monkeypatch):
    monitor = CryptoMonitor()
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    ws = SimpleNamespace(symbol="XAUT/USD", watchlist_source_id=None)
    signal = SimpleNamespace(
        symbol="XAUT/USD",
        strategy="Pullback Reclaim",
        strategy_key="pullback_reclaim",
        entry_price=4600.0,
        initial_stop=4550.0,
        profit_target_1=4700.0,
        profit_target_2=4800.0,
        max_hold_hours=6,
        regime="trending_up",
        confidence=0.82,
        notes="",
        reasoning={},
    )

    monkeypatch.setattr("app.crypto.monitoring.runtime_state.get_trading_mode", AsyncMock(return_value="paper"))
    monkeypatch.setattr("app.crypto.monitoring.runtime_state.get_risk_per_trade_pct", AsyncMock(return_value=0.005))
    monkeypatch.setattr("app.common.paper_ledger.size_paper_position", AsyncMock(return_value=0.0))

    await monitor._create_position(db, ws, signal, "XAUT/USD")

    assert db.add.call_count == 0
    assert db.flush.await_count == 0
