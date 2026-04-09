"""watchlist_symbols composite index

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Covers: WHERE asset_class = ? AND state = ?
    # Used by: StockMonitor._cycle() and CryptoMonitor._cycle() per-cycle symbol load
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_watchlist_symbols_asset_class_state"
        " ON watchlist_symbols (asset_class, state)"
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_symbols_asset_class_state", table_name="watchlist_symbols")
