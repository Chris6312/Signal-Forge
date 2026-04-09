"""convert native enum columns to varchar for asyncpg compatibility

Revision ID: 0004
Revises: 0003
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    # Convert every native PostgreSQL enum column to VARCHAR so that asyncpg
    # can bind Python str values without needing a registered type codec.
    # The USING clause preserves all existing row data during the cast.
    op.execute("ALTER TABLE positions          ALTER COLUMN state      TYPE VARCHAR(50) USING state::text")
    op.execute("ALTER TABLE watchlist_symbols  ALTER COLUMN state      TYPE VARCHAR(50) USING state::text")
    op.execute("ALTER TABLE orders             ALTER COLUMN order_type TYPE VARCHAR(50) USING order_type::text")
    op.execute("ALTER TABLE orders             ALTER COLUMN side       TYPE VARCHAR(50) USING side::text")
    op.execute("ALTER TABLE orders             ALTER COLUMN status     TYPE VARCHAR(50) USING status::text")
    op.execute("ALTER TABLE ledger_entries     ALTER COLUMN entry_type TYPE VARCHAR(50) USING entry_type::text")
    op.execute("ALTER TABLE audit_events       ALTER COLUMN source     TYPE VARCHAR(50) USING source::text")

    # Drop the now-unused native enum types.
    op.execute("DROP TYPE IF EXISTS positionstate")
    op.execute("DROP TYPE IF EXISTS symbolstate")
    op.execute("DROP TYPE IF EXISTS ordertype")
    op.execute("DROP TYPE IF EXISTS orderside")
    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS entrytype")
    op.execute("DROP TYPE IF EXISTS auditsource")


def downgrade():
    op.execute("CREATE TYPE positionstate AS ENUM ('PENDING', 'OPEN', 'CLOSED')")
    op.execute("CREATE TYPE symbolstate   AS ENUM ('ACTIVE', 'MANAGED', 'INACTIVE')")
    op.execute("CREATE TYPE ordertype     AS ENUM ('ENTRY', 'EXIT', 'STOP', 'LIMIT', 'PARTIAL_EXIT')")
    op.execute("CREATE TYPE orderside     AS ENUM ('BUY', 'SELL')")
    op.execute("CREATE TYPE orderstatus   AS ENUM ('PENDING', 'SUBMITTED', 'FILLED', 'PARTIALLY_FILLED', 'CANCELLED', 'REJECTED')")
    op.execute("CREATE TYPE entrytype     AS ENUM ('FILL', 'FEE', 'ADJUSTMENT', 'RECONCILIATION', 'INITIAL_DEPOSIT')")
    op.execute("CREATE TYPE auditsource   AS ENUM ('SYSTEM', 'DISCORD', 'USER', 'BROKER', 'WORKER')")

    op.execute("ALTER TABLE positions         ALTER COLUMN state      TYPE positionstate USING state::positionstate")
    op.execute("ALTER TABLE watchlist_symbols ALTER COLUMN state      TYPE symbolstate   USING state::symbolstate")
    op.execute("ALTER TABLE orders            ALTER COLUMN order_type TYPE ordertype     USING order_type::ordertype")
    op.execute("ALTER TABLE orders            ALTER COLUMN side       TYPE orderside     USING side::orderside")
    op.execute("ALTER TABLE orders            ALTER COLUMN status     TYPE orderstatus   USING status::orderstatus")
    op.execute("ALTER TABLE ledger_entries    ALTER COLUMN entry_type TYPE entrytype     USING entry_type::entrytype")
    op.execute("ALTER TABLE audit_events      ALTER COLUMN source     TYPE auditsource   USING source::auditsource")
