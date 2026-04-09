"""
market_hours.py — NYSE trading-day and session-window utilities.

All logic is expressed in Eastern Time (ET) so it handles both
EDT (UTC-4) and EST (UTC-5) transparently via the IANA tz database.

Session windows
---------------
  pre_market   08:30 – 09:30 ET  Pull candles / backfill / prep signals, no new entries
  open         09:30 – 15:50 ET  Active trading; entries and exits both live
  eod          15:50 – 16:00 ET  EOD exits only; no new entries allowed
  closed       everything else   All stock operations suspended
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")

_PREP_START   = dt_time(8, 30)   # begin candle pull / backfill / signal prep
_MARKET_OPEN  = dt_time(9, 30)   # NYSE regular session open
_EOD_CUTOFF   = dt_time(15, 50)  # stop new entries, begin EOD exits
_MARKET_CLOSE = dt_time(16, 0)   # NYSE regular session close


# ---------------------------------------------------------------------------
# Internal calendar helpers
# ---------------------------------------------------------------------------

def _observed(d: date) -> date:
    """Shift a Saturday holiday to Friday, a Sunday holiday to Monday."""
    if d.weekday() == 5:          # Saturday → previous Friday
        return d - timedelta(days=1)
    if d.weekday() == 6:          # Sunday   → following Monday
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the n-th (1-based) occurrence of *weekday* (Mon=0) in *month*."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of *weekday* (Mon=0) in *month*."""
    first_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last = first_next - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _easter(year: int) -> date:
    """Compute Easter Sunday via the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _nyse_holidays(year: int) -> frozenset[date]:
    """Return the complete set of NYSE market holidays for *year*."""
    good_friday = _easter(year) - timedelta(days=2)
    return frozenset({
        _observed(date(year,  1,  1)),               # New Year's Day
        _nth_weekday(year,    1,  0, 3),             # MLK Jr. Day  (3rd Mon Jan)
        _nth_weekday(year,    2,  0, 3),             # Presidents'  (3rd Mon Feb)
        good_friday,                                  # Good Friday
        _last_weekday_of_month(year, 5, 0),           # Memorial Day (last Mon May)
        _observed(date(year,  6, 19)),               # Juneteenth
        _observed(date(year,  7,  4)),               # Independence Day
        _nth_weekday(year,    9,  0, 1),             # Labor Day    (1st Mon Sep)
        _nth_weekday(year,   11,  3, 4),             # Thanksgiving (4th Thu Nov)
        _observed(date(year, 12, 25)),               # Christmas Day
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_trading_day(d: date | None = None) -> bool:
    """Return True if *d* (defaults to today ET) is a NYSE trading day."""
    if d is None:
        d = datetime.now(_EASTERN).date()
    if d.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    return d not in _nyse_holidays(d.year)


def market_status() -> str:
    """
    Return the current NYSE session window as a string.

    ``"closed"``     Non-trading day, or before 09:15 / after 16:00 ET.
    ``"pre_market"`` 09:15–09:30 ET on a trading day — pull candles, prep signals.
    ``"open"``       09:30–15:50 ET on a trading day — entries and exits live.
    ``"eod"``        15:50–16:00 ET on a trading day — EOD exits only.
    """
    now_et = datetime.now(_EASTERN)
    if not is_trading_day(now_et.date()):
        return "closed"
    t = now_et.time()
    if t < _PREP_START:
        return "closed"
    if t < _MARKET_OPEN:
        return "pre_market"
    if t < _EOD_CUTOFF:
        return "open"
    if t < _MARKET_CLOSE:
        return "eod"
    return "closed"   # past 16:00 ET


def is_market_open() -> bool:
    """True only during the active trading window (09:30–15:50 ET)."""
    return market_status() == "open"


def is_pre_market_prep() -> bool:
    """True during 09:15–09:30 ET — candle pull / signal prep, no entries."""
    return market_status() == "pre_market"


def is_near_eod() -> bool:
    """
    True from 15:50 to 16:00 ET on a trading day.
    Signals exit strategies to close all open intraday positions.
    """
    return market_status() == "eod"


def can_enter_trade() -> bool:
    """
    True only when it is safe to open a new position (09:30–15:50 ET).
    Equivalent to ``is_market_open()``; named expressively for entry guards.
    """
    return market_status() == "open"


def can_pull_data() -> bool:
    """
    True whenever the bot should be active at all (09:15–16:00 ET on trading days).
    Gate any stock worker cycle with this to prevent wasteful after-hours API calls.
    """
    return market_status() in ("pre_market", "open", "eod")
