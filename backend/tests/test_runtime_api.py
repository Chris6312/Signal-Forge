from unittest.mock import AsyncMock

import pytest

from app.api.deps import require_admin
from app.api.routes import runtime as runtime_route
from app.main import app


@pytest.fixture
def allow_admin():
    app.dependency_overrides[require_admin] = lambda: None
    yield
    app.dependency_overrides.pop(require_admin, None)


@pytest.mark.usefixtures("api_client")
class TestRuntimeApi:
    def test_get_returns_asset_specific_risk_fields_with_patch1_defaults(self, api_client, monkeypatch):
        monkeypatch.setattr(
            runtime_route.runtime_state,
            "get_state",
            AsyncMock(
                return_value={
                    "status": "online",
                    "trading_enabled": True,
                    "crypto_trading_enabled": True,
                    "stock_trading_enabled": True,
                    "trading_mode": "paper",
                    "max_crypto_positions": 5,
                    "max_stock_positions": 5,
                    "crypto_monitor": "idle",
                    "stock_monitor": "idle",
                    "crypto_exit_worker": "idle",
                    "stock_exit_worker": "idle",
                    "discord_listener": "idle",
                }
            ),
        )
        monkeypatch.setattr(
            runtime_route.runtime_state,
            "get_risk_per_trade_pct",
            AsyncMock(side_effect=lambda asset_class=None: 0.004 if asset_class == "crypto" else 0.005),
        )

        response = api_client.get("/api/runtime")
        assert response.status_code == 200
        data = response.json()
        assert data["risk_per_trade_pct_stocks"] == pytest.approx(0.005)
        assert data["risk_per_trade_pct_crypto"] == pytest.approx(0.004)
        assert "risk_per_trade_pct" not in data

    def test_patch_persists_asset_specific_risk_fields(self, api_client, monkeypatch, allow_admin):
        state = {
            "status": "online",
            "trading_enabled": True,
            "crypto_trading_enabled": True,
            "stock_trading_enabled": True,
            "trading_mode": "paper",
            "risk_per_trade_pct_stocks": 0.005,
            "risk_per_trade_pct_crypto": 0.004,
            "max_crypto_positions": 5,
            "max_stock_positions": 5,
            "crypto_monitor": "idle",
            "stock_monitor": "idle",
            "crypto_exit_worker": "idle",
            "stock_exit_worker": "idle",
            "discord_listener": "idle",
        }

        async def fake_get_state():
            return dict(state)

        async def fake_set_value(key, value):
            state[key] = value

        async def fake_get_risk(asset_class=None):
            return state["risk_per_trade_pct_crypto"] if asset_class == "crypto" else state["risk_per_trade_pct_stocks"]

        monkeypatch.setattr(runtime_route.runtime_state, "get_state", AsyncMock(side_effect=fake_get_state))
        monkeypatch.setattr(runtime_route.runtime_state, "set_value", AsyncMock(side_effect=fake_set_value))
        monkeypatch.setattr(runtime_route.runtime_state, "get_risk_per_trade_pct", AsyncMock(side_effect=fake_get_risk))

        response = api_client.patch(
            "/api/runtime",
            json={
                "risk_per_trade_pct_stocks": 0.006,
                "risk_per_trade_pct_crypto": 0.005,
                "max_crypto_positions": 9,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["risk_per_trade_pct_stocks"] == pytest.approx(0.006)
        assert data["risk_per_trade_pct_crypto"] == pytest.approx(0.005)
        assert state["risk_per_trade_pct_stocks"] == pytest.approx(0.006)
        assert state["risk_per_trade_pct_crypto"] == pytest.approx(0.005)
        assert state["max_crypto_positions"] == 9

    def test_patch_rejects_legacy_scalar_risk_field(self, api_client, allow_admin):
        response = api_client.patch(
            "/api/runtime",
            json={"risk_per_trade_pct": 0.02},
        )
        assert response.status_code == 422
