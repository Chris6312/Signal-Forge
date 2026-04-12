from __future__ import annotations

from typing import Any


def build_runtime_visibility_payload(reasoning: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reasoning, dict):
        return {}

    risk_multipliers = reasoning.get("risk_multipliers")
    payload = {"risk_multipliers": risk_multipliers} if risk_multipliers is not None else {}

    risk_controls: dict[str, Any] = {}
    if reasoning.get("risk_multipliers") is not None:
        risk_controls["risk_multipliers"] = reasoning["risk_multipliers"]
    if reasoning.get("volatility_pct") is not None:
        risk_controls["volatility_pct"] = reasoning["volatility_pct"]
    if reasoning.get("signal_maturity"):
        risk_controls["maturity_state"] = reasoning["signal_maturity"]
    if reasoning.get("regime"):
        risk_controls["regime_state"] = reasoning["regime"]

    if risk_controls:
        payload["risk_controls"] = risk_controls

    return payload
