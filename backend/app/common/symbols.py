"""Canonical symbol utilities used across the system.

Provides a single truth for crypto symbols so variants like "XBTUSD",
"XBT/USD", and "BTC/USD" collapse to a single canonical identity.

Functions are intentionally small and defensive — they won't raise on
malformed input and will return a best-effort normalization.
"""
from __future__ import annotations

import re
from typing import Tuple


def _split_pair(symbol: str) -> Tuple[str, str] | None:
    s = (symbol or "").strip().upper()
    if not s:
        return None
    # Normalize common separators
    s = s.replace("-", "/").replace("_", "/")
    if "/" in s:
        parts = s.split("/")
        if len(parts) >= 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
        return None

    # If no separator, try to split by typical market conventions.
    # Commonly base is 3 or more letters and quote is 3 letters (e.g. BTCUSD, ETHUSD)
    m = re.match(r"^([A-Z]{3,})([A-Z]{3,})$", s)
    if m:
        return m.group(1), m.group(2)

    return None


def canonical_symbol(symbol: str | None, asset_class: str | None = None) -> str:
    """Return the canonical display identity for a symbol.

    For crypto we prefer the form "BASE/QUOTE" with common aliases
    normalized (e.g. XBT -> BTC). For non-crypto symbols we return
    a simple uppercase string.
    """
    if not symbol:
        return ""
    s = symbol.strip()
    if not s:
        return ""
    ac = (asset_class or "").lower()
    if ac == "crypto":
        parts = _split_pair(s)
        if not parts:
            return s.upper()
        base, quote = parts
        # Map exchange/display aliases to canonical base
        if base == "XBT":
            base = "BTC"
        # Return in BASE/QUOTE form
        return f"{base}/{quote}"
    else:
        return s.upper()


def kraken_provider_pair(canonical: str) -> str:
    """Map a canonical symbol to Kraken's pair representation.

    Kraken historically uses "XBT" instead of "BTC" and often expects no
    separator (e.g. "XBTUSD"). This function will attempt to convert a
    canonical "BASE/QUOTE" string into the provider-specific form.
    Falls back to removing any separators and uppercasing.
    """
    if not canonical:
        return ""
    s = canonical.strip().upper()
    parts = _split_pair(s)
    if parts:
        base, quote = parts
        if base == "BTC":
            base = "XBT"
        return f"{base}{quote}"
    # Last resort: remove non-alphanumerics
    return re.sub(r"[^A-Z0-9]", "", s)
