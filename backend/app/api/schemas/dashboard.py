from pydantic import BaseModel


class PnlSummary(BaseModel):
    asset_class: str
    realized_pnl: float
    unrealized_pnl: float
    cash_balance: float
    fees_total: float
    open_positions: int


class DashboardOut(BaseModel):
    system_status: str
    trading_enabled: bool
    crypto_trading_enabled: bool
    stock_trading_enabled: bool
    crypto_monitor: str
    stock_monitor: str
    crypto_exit_worker: str
    stock_exit_worker: str
    discord_listener: str
    last_heartbeat: str | None = None
    pnl: list[PnlSummary]
    total_open_positions: int
    active_watchlist_count: int
    managed_watchlist_count: int
