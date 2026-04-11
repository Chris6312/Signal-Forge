"""actually add missing regime columns to bot_strategy_decisions

Revision ID: 65dd3d64ecc6
Revises: 4e244d79f890
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "65dd3d64ecc6"
down_revision: Union[str, None] = "4e244d79f890"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("bot_strategy_decisions")}

    if "regime_applied" not in columns:
        op.add_column(
            "bot_strategy_decisions",
            sa.Column("regime_applied", sa.String(), nullable=True),
        )

    if "weight_profile" not in columns:
        op.add_column(
            "bot_strategy_decisions",
            sa.Column("weight_profile", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("bot_strategy_decisions")}

    if "weight_profile" in columns:
        op.drop_column("bot_strategy_decisions", "weight_profile")

    if "regime_applied" in columns:
        op.drop_column("bot_strategy_decisions", "regime_applied")