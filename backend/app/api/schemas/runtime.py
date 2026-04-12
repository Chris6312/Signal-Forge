from pydantic import BaseModel, ConfigDict


class RuntimeStateOut(BaseModel):
    status: str
    trading_enabled: bool
    crypto_trading_enabled: bool
    stock_trading_enabled: bool
    trading_mode: str = "paper"
    risk_per_trade_pct_stocks: float = 0.005
    risk_per_trade_pct_crypto: float = 0.004
    max_crypto_positions: int
    max_stock_positions: int
    crypto_monitor: str
    stock_monitor: str
    crypto_exit_worker: str
    stock_exit_worker: str
    discord_listener: str
    last_heartbeat: str | None = None
    started_at: str | None = None


class RuntimeUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trading_enabled: bool | None = None
    crypto_trading_enabled: bool | None = None
    stock_trading_enabled: bool | None = None
    trading_mode: str | None = None
    risk_per_trade_pct_stocks: float | None = None
    risk_per_trade_pct_crypto: float | None = None
    max_crypto_positions: int | None = None
    max_stock_positions: int | None = None
