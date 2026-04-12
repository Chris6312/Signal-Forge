from app.common.runtime_visibility import build_runtime_visibility_payload


def test_runtime_visibility_passes_through_risk_multipliers():
    reasoning = {
        "risk_multipliers": {
            "volatility_multiplier": 0.84,
            "drawdown_multiplier": 0.75,
            "cluster_multiplier": 0.9,
            "concentration_multiplier": 0.8,
            "regime_multiplier": 1.05,
            "effective_risk_multiplier": 0.47,
        }
    }

    payload = build_runtime_visibility_payload(reasoning)

    assert payload == {"risk_multipliers": reasoning["risk_multipliers"]}


def test_runtime_visibility_omits_risk_multipliers_when_absent():
    payload = build_runtime_visibility_payload({"position_size_pct": 0.5})

    assert payload == {}
    assert "risk_multipliers" not in payload
