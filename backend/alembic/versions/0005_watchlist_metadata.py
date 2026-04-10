"""add reason/confidence/tags to watchlist_symbols

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable columns to avoid locking existing writes; data will be backfilled by processes if needed.
    op.add_column('watchlist_symbols', sa.Column('reason', sa.Text(), nullable=True))
    op.add_column('watchlist_symbols', sa.Column('confidence', sa.Float(), nullable=True))
    # JSONB type for tags; use postgresql.JSONB if available
    try:
        from sqlalchemy.dialects import postgresql
        op.add_column('watchlist_symbols', sa.Column('tags', postgresql.JSONB(), nullable=True))
    except Exception:
        op.add_column('watchlist_symbols', sa.Column('tags', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('watchlist_symbols', 'tags')
    op.drop_column('watchlist_symbols', 'confidence')
    op.drop_column('watchlist_symbols', 'reason')
