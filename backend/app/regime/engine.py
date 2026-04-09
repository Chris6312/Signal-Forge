import logging
from dataclasses import dataclass

from .classifier import classify_stock_regime, classify_crypto_regime
from .indicators import AssetIndicators, VixIndicators
from .policy import RegimePolicy, STOCK_REGIME_POLICIES, CRYPTO_REGIME_POLICIES

logger = logging.getLogger(__name__)

_CONFIRM_THRESHOLD = 2


@dataclass
class _RegimeState:
    confirmed: str = "NEUTRAL"
    candidate: str = "NEUTRAL"
    candidate_count: int = 0
    last_score: int = 0


def _tick(state: _RegimeState, new_label: str, score: int, threshold: int) -> None:
    state.last_score = score

    if new_label == state.confirmed:
        state.candidate = new_label
        state.candidate_count = 0
        return

    if new_label == state.candidate:
        state.candidate_count += 1
    else:
        state.candidate = new_label
        state.candidate_count = 1

    if state.candidate_count >= threshold:
        state.confirmed = state.candidate
        state.candidate_count = 0


class RegimeEngine:
    def __init__(self, confirm_threshold: int = _CONFIRM_THRESHOLD) -> None:
        self._confirm_threshold = confirm_threshold
        self._stocks = _RegimeState()
        self._crypto = _RegimeState()

    def update_stocks(self, spy: AssetIndicators, vix: VixIndicators) -> str:
        label, score = classify_stock_regime(spy, vix)
        _tick(self._stocks, label, score, self._confirm_threshold)
        logger.info("Stock regime → confirmed=%s  score=%d", self._stocks.confirmed, score)
        return self._stocks.confirmed

    def update_crypto(self, btc: AssetIndicators, eth: AssetIndicators) -> str:
        label, score = classify_crypto_regime(btc, eth)
        _tick(self._crypto, label, score, self._confirm_threshold)
        logger.info("Crypto regime → confirmed=%s  score=%d", self._crypto.confirmed, score)
        return self._crypto.confirmed

    @property
    def stock_regime(self) -> str:
        return self._stocks.confirmed

    @property
    def crypto_regime(self) -> str:
        return self._crypto.confirmed

    @property
    def stock_policy(self) -> RegimePolicy:
        return STOCK_REGIME_POLICIES[self._stocks.confirmed]

    @property
    def crypto_policy(self) -> RegimePolicy:
        return CRYPTO_REGIME_POLICIES[self._crypto.confirmed]

    def policy_for(self, asset_class: str) -> RegimePolicy:
        if asset_class.lower() == "stock":
            return self.stock_policy
        if asset_class.lower() == "crypto":
            return self.crypto_policy
        raise ValueError(f"Unknown asset class: {asset_class!r}")

    def can_open(
        self,
        asset_class: str,
        strategy: str,
        setup_score: float,
        current_open_positions: int,
    ) -> tuple[bool, str]:
        policy = self.policy_for(asset_class)

        if not policy.allow_new_entries:
            return False, "new entries disabled by regime"

        if current_open_positions >= policy.max_positions:
            regime = self.stock_regime if asset_class.lower() == "stock" else self.crypto_regime
            return False, f"at max positions ({policy.max_positions}) for {regime}"

        if setup_score < policy.min_setup_score:
            return False, f"setup score {setup_score:.2f} below regime minimum {policy.min_setup_score:.2f}"

        strat = strategy.lower()
        if "breakout" in strat and not policy.breakout_enabled:
            return False, "breakout strategy disabled in current regime"

        if "mean_reversion" in strat and not policy.mean_reversion_enabled:
            return False, "mean reversion disabled in current regime"

        return True, "ok"


regime_engine = RegimeEngine()
