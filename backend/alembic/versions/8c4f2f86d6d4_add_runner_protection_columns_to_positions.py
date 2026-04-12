"""add runner protection columns to positions

Revision ID: 8c4f2f86d6d4
Revises: 7d502b101add
Create Date: 2026-04-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "8c4f2f86d6d4"
down_revision: Union[str, None] = "7d502b101add"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNS = (
    ("protection_mode", sa.String(length=30)),
    ("initial_risk_price", sa.Float()),
    ("tp1_price", sa.Float()),
    ("tp1_hit", sa.Boolean()),
    ("break_even_floor", sa.Float()),
    ("promoted_floor", sa.Float()),
    ("highest_promoted_floor", sa.Float()),
    ("runner_phase", sa.String(length=30)),
    ("milestone_version", sa.String(length=20)),
    ("last_protection_update_at", sa.DateTime()),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("positions")}

    for name, type_ in COLUMNS:
        if name not in columns:
            op.add_column(
                "positions",
                sa.Column(name, type_, nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("positions")}

    for name, _ in reversed(COLUMNS):
        if name in columns:
            op.drop_column("positions", name)
