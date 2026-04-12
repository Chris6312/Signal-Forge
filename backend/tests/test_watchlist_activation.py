from datetime import datetime

from app.common.watchlist_activation import activation_ready_at, is_watchlist_activation_ready


def test_activation_ready_at_waits_for_next_15m_boundary_plus_buffer():
    added_at = datetime(2026, 4, 12, 1, 13, 31)
    assert activation_ready_at(added_at) == datetime(2026, 4, 12, 1, 15, 20)



def test_activation_ready_at_rolls_to_following_boundary_when_added_exactly_on_boundary():
    added_at = datetime(2026, 4, 12, 1, 15, 0)
    assert activation_ready_at(added_at) == datetime(2026, 4, 12, 1, 30, 20)



def test_is_watchlist_activation_ready_respects_gate():
    added_at = datetime(2026, 4, 12, 1, 13, 31)
    assert is_watchlist_activation_ready(added_at, now=datetime(2026, 4, 12, 1, 15, 19)) is False
    assert is_watchlist_activation_ready(added_at, now=datetime(2026, 4, 12, 1, 15, 20)) is True
