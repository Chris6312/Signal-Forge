from datetime import datetime, timezone

from app.common.watchlist_activation import activation_ready_at, is_watchlist_activation_ready


def test_activation_ready_at_waits_for_next_15m_boundary_plus_buffer():
    added_at = datetime(2026, 4, 12, 1, 13, 31)
    assert activation_ready_at(added_at) == datetime(2026, 4, 12, 1, 15, 20)



def test_activation_ready_at_rolls_to_following_boundary_when_added_exactly_on_boundary():
    added_at = datetime(2026, 4, 12, 1, 15, 0)
    assert activation_ready_at(added_at) == datetime(2026, 4, 12, 1, 30, 20)


def test_activation_ready_at_supports_5m_candles_for_stocks():
    added_at = datetime(2026, 4, 12, 1, 13, 31)
    assert activation_ready_at(added_at, fast_tf_minutes=5) == datetime(2026, 4, 12, 1, 15, 20)



def test_is_watchlist_activation_ready_respects_gate():
    added_at = datetime(2026, 4, 12, 1, 13, 31)
    assert is_watchlist_activation_ready(added_at, now=datetime(2026, 4, 12, 1, 15, 19)) is False
    assert is_watchlist_activation_ready(added_at, now=datetime(2026, 4, 12, 1, 15, 20)) is True


def test_watchlist_update_requires_post_update_15m_ingestion_for_crypto():
    added_at = datetime(2026, 4, 12, 1, 15, 1)
    frame_info = {"last_close_ts": datetime(2026, 4, 12, 1, 15, 0, tzinfo=timezone.utc).timestamp(), "last_ingested_ts": datetime(2026, 4, 12, 1, 15, 20, tzinfo=timezone.utc).timestamp()}
    assert is_watchlist_activation_ready(
        added_at,
        now=datetime(2026, 4, 12, 1, 15, 20),
        fast_tf_minutes=15,
        frame_info=frame_info,
    ) is False


def test_crypto_waits_for_next_ingested_15m_candle():
    added_at = datetime(2026, 4, 12, 1, 13, 31)
    frame_info = {"last_close_ts": datetime(2026, 4, 12, 1, 15, 0, tzinfo=timezone.utc).timestamp(), "last_ingested_ts": datetime(2026, 4, 12, 1, 15, 20, tzinfo=timezone.utc).timestamp()}
    assert is_watchlist_activation_ready(
        added_at,
        now=datetime(2026, 4, 12, 1, 15, 20),
        fast_tf_minutes=15,
        frame_info=frame_info,
    ) is True


def test_stocks_wait_for_next_ingested_5m_candle():
    added_at = datetime(2026, 4, 12, 1, 3, 31)
    frame_info = {"last_close_ts": datetime(2026, 4, 12, 1, 5, 0, tzinfo=timezone.utc).timestamp(), "last_ingested_ts": datetime(2026, 4, 12, 1, 5, 20, tzinfo=timezone.utc).timestamp()}
    assert is_watchlist_activation_ready(
        added_at,
        now=datetime(2026, 4, 12, 1, 5, 20),
        fast_tf_minutes=5,
        frame_info=frame_info,
    ) is True


def test_reactivated_symbols_also_wait_for_next_fast_candle():
    added_at = datetime(2026, 4, 12, 1, 5, 1)
    frame_info = {"last_close_ts": datetime(2026, 4, 12, 1, 5, 0, tzinfo=timezone.utc).timestamp(), "last_ingested_ts": datetime(2026, 4, 12, 1, 5, 20, tzinfo=timezone.utc).timestamp()}
    assert is_watchlist_activation_ready(
        added_at,
        now=datetime(2026, 4, 12, 1, 5, 20),
        fast_tf_minutes=5,
        frame_info=frame_info,
    ) is False
