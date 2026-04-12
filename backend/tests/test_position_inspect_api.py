from types import SimpleNamespace
from uuid import uuid4


def test_position_api_returns_tp1_milestone_and_promoted_floor(api_client, mock_db):
    db, result = mock_db
    position = SimpleNamespace(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state="OPEN",
        entry_price=100.0,
        current_price=108.0,
        quantity=5.0,
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={
            "tp1_hit": True,
            "tp1_price": 108.0,
            "protected_floor": 100.0,
            "trailing_stop": 100.0,
            "protection_mode": "break_even",
            "be_promoted": True,
            "trail_active": True,
        },
    )
    result.scalar_one_or_none.return_value = position

    response = api_client.get(f"/api/positions/{position.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["milestone_state"]["tp1_hit"] is True
    assert payload["milestone_state"]["protected_floor"] == 100.0
    assert payload["milestone_state"]["protection_mode"] == "break_even"
    assert payload["current_stop"] == 100.0
