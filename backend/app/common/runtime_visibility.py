from __future__ import annotations

from typing import Any


def build_runtime_visibility_payload(reasoning: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reasoning, dict):
        return {}

    risk_multipliers = reasoning.get("risk_multipliers")
    return {"risk_multipliers": risk_multipliers} if risk_multipliers is not None else {}
