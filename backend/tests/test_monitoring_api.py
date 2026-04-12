from types import SimpleNamespace

from app.api.routes.monitoring import _select_top_signal, _strategy_key


def test_strategy_key_normalizes_labels_and_keys():
    assert _strategy_key("Pullback Reclaim") == "pullback_reclaim"
    assert _strategy_key("trend_continuation") == "trend_continuation"


def test_select_top_signal_prefers_backend_top_strategy():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = _select_top_signal([first, second], "trend_continuation")

    assert selected is second


def test_select_top_signal_falls_back_to_first_signal_when_backend_top_strategy_missing():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = _select_top_signal([first, second], None)

    assert selected is first
