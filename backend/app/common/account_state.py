from __future__ import annotations

from app.common.runtime_state import runtime_state


def compute_drawdown_pct(current_equity: float, peak_equity: float) -> float:
    try:
        current = float(current_equity)
        peak = float(peak_equity)
    except (TypeError, ValueError):
        return 0.0
    if current <= 0 or peak <= 0:
        return 0.0
    if current >= peak:
        return 0.0
    return max(0.0, (peak - current) / peak)


def drawdown_multiplier(drawdown_pct: float) -> float:
    if drawdown_pct < 0.03:
        return 1.0
    if drawdown_pct < 0.06:
        return 0.75
    if drawdown_pct <= 0.10:
        return 0.50
    return 0.25


def should_block_new_entries(drawdown_pct: float) -> bool:
    return drawdown_pct > 0.15


def _peak_equity_key(asset_class: str) -> str:
    asset = (asset_class or "").strip().lower()
    if asset in ("stocks", "stock"):
        asset = "stock"
    elif asset in ("crypto", "cryptos", "digital"):
        asset = "crypto"
    return f"peak_equity_{asset}"


async def get_peak_equity(asset_class: str, current_equity: float | None = None) -> float:
    key = _peak_equity_key(asset_class)
    stored = await runtime_state.get_value(key, None)
    try:
        stored_value = float(stored) if stored is not None else 0.0
    except (TypeError, ValueError):
        stored_value = 0.0

    try:
        current_value = float(current_equity) if current_equity is not None else None
    except (TypeError, ValueError):
        current_value = None

    if current_value is not None and current_value > stored_value:
        await runtime_state.set_value(key, current_value)
        return current_value

    if stored_value <= 0 and current_value is not None:
        await runtime_state.set_value(key, current_value)
        return current_value

    return stored_value if stored_value > 0 else float(current_value or 0.0)


async def note_peak_equity(asset_class: str, current_equity: float) -> float:
    return await get_peak_equity(asset_class, current_equity)
