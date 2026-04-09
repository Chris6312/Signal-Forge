"""Integration tests for FastAPI route handlers using a mocked DB session."""
import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.api.deps import get_db_session


# ---------------------------------------------------------------------------
# Shared client fixture (uses a fresh mock DB per test class)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = 0
    db.execute = AsyncMock(return_value=result)
    return db, result


@pytest.fixture
def client(mock_db):
    db, _ = mock_db

    async def _override():
        yield db

    app.dependency_overrides[get_db_session] = _override
    yield TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "app" in data
        assert "version" in data


# ---------------------------------------------------------------------------
# Trades  —  GET /api/trades
# ---------------------------------------------------------------------------

class TestTrades:
    def test_returns_empty_list(self, client):
        response = client.get("/api/trades")
        assert response.status_code == 200
        assert response.json() == []

    def test_accepts_asset_class_filter(self, client):
        response = client.get("/api/trades?asset_class=crypto")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_accepts_limit_param(self, client):
        response = client.get("/api/trades?limit=10")
        assert response.status_code == 200

    def test_rejects_limit_above_max(self, client):
        response = client.get("/api/trades?limit=999")
        assert response.status_code == 422  # Unprocessable Entity


class TestTradeSummary:
    def test_empty_summary_defaults(self, client):
        response = client.get("/api/trades/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_trades"] == 0
        assert data["winners"] == 0
        assert data["losers"] == 0
        assert data["win_rate"] == pytest.approx(0.0)
        assert data["total_pnl"] == pytest.approx(0.0)
        assert data["avg_pnl"] == pytest.approx(0.0)

    def test_accepts_asset_class_filter(self, client):
        response = client.get("/api/trades/summary?asset_class=stock")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Positions  —  GET /api/positions
# ---------------------------------------------------------------------------

class TestPositions:
    def test_returns_empty_list(self, client):
        response = client.get("/api/positions")
        assert response.status_code == 200
        assert response.json() == []

    def test_accepts_state_filter(self, client):
        response = client.get("/api/positions?state=OPEN")
        assert response.status_code == 200

    def test_accepts_asset_class_filter(self, client):
        response = client.get("/api/positions?asset_class=crypto")
        assert response.status_code == 200

    def test_accepts_combined_filters(self, client):
        response = client.get("/api/positions?asset_class=stock&state=OPEN")
        assert response.status_code == 200

    def test_open_positions_empty(self, client):
        response = client.get("/api/positions/open")
        assert response.status_code == 200
        assert response.json() == []

    def test_position_not_found_returns_404(self, client):
        response = client.get(f"/api/positions/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_position_orders_not_found_returns_empty(self, client):
        # Orders query returns empty list for an unknown position
        response = client.get(f"/api/positions/{uuid.uuid4()}/orders")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Watchlist  —  GET /api/watchlist
# ---------------------------------------------------------------------------

class TestWatchlist:
    def test_returns_empty_list(self, client):
        response = client.get("/api/watchlist")
        assert response.status_code == 200
        assert response.json() == []

    def test_accepts_state_filter(self, client):
        response = client.get("/api/watchlist?state=ACTIVE")
        assert response.status_code == 200

    def test_accepts_asset_class_filter(self, client):
        response = client.get("/api/watchlist?asset_class=crypto")
        assert response.status_code == 200

    def test_active_symbols_empty(self, client):
        response = client.get("/api/watchlist/active")
        assert response.status_code == 200
        assert response.json() == []

    def test_symbol_not_found_returns_404(self, client):
        response = client.get(f"/api/watchlist/{uuid.uuid4()}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Ledger  —  GET /api/ledger
# ---------------------------------------------------------------------------

class TestLedger:
    def test_accounts_returns_empty_list(self, client):
        response = client.get("/api/ledger/accounts")
        assert response.status_code == 200
        assert response.json() == []

    def test_entries_returns_empty_list(self, client):
        response = client.get("/api/ledger/entries")
        assert response.status_code == 200
        assert response.json() == []

    def test_entries_accepts_asset_class_filter(self, client):
        response = client.get("/api/ledger/entries?asset_class=crypto")
        assert response.status_code == 200

    def test_entries_accepts_limit_param(self, client):
        response = client.get("/api/ledger/entries?limit=50")
        assert response.status_code == 200
