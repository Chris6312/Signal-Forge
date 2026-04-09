"""positions composite indexes

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Covers: WHERE asset_class = ? AND state = ?
    # Used by: _count_open_positions (stock + crypto), exit-worker full load
    op.create_index(
        "ix_positions_asset_class_state",
        "positions",
        ["asset_class", "state"],
    )

    # Covers: WHERE symbol = ? AND asset_class = ? AND state = ?
    # Used by: _has_open_position (stock + crypto monitors, watchlist engine)
    #          WHERE symbol IN (...) AND state = ? (watchlist batch check)
    op.create_index(
        "ix_positions_symbol_asset_class_state",
        "positions",
        ["symbol", "asset_class", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_positions_symbol_asset_class_state", table_name="positions")
    op.drop_index("ix_positions_asset_class_state", table_name="positions")
