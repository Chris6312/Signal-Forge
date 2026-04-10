"""add regime fields to bot decision

Revision ID: b7c4fd4efc7d
Revises: 0006
Create Date: 2026-04-10 17:57:36.882568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c4fd4efc7d'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_strategy_decisions",
        sa.Column("regime_applied", sa.String(), nullable=True),
    )
    op.add_column(
        "bot_strategy_decisions",
        sa.Column("weight_profile", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bot_strategy_decisions", "weight_profile")
    op.drop_column("bot_strategy_decisions", "regime_applied")