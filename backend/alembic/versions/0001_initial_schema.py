"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_symbols",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("asset_class", sa.String(10), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("watchlist_source_id", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("added_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("removed_at", sa.DateTime, nullable=True),
        sa.Column("managed_since", sa.DateTime, nullable=True),
        sa.Column("closed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_watchlist_symbols_symbol", "watchlist_symbols", ["symbol"])
    op.create_index("ix_watchlist_symbols_state", "watchlist_symbols", ["state"])

    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("asset_class", sa.String(10), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("entry_price", sa.Float, nullable=True),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("entry_time", sa.DateTime, nullable=True),
        sa.Column("entry_strategy", sa.String(100), nullable=True),
        sa.Column("exit_strategy", sa.String(100), nullable=True),
        sa.Column("initial_stop", sa.Float, nullable=True),
        sa.Column("profit_target_1", sa.Float, nullable=True),
        sa.Column("profit_target_2", sa.Float, nullable=True),
        sa.Column("max_hold_hours", sa.Integer, nullable=True),
        sa.Column("regime_at_entry", sa.String(50), nullable=True),
        sa.Column("watchlist_source_id", sa.String(100), nullable=True),
        sa.Column("management_policy_version", sa.String(20), nullable=True),
        sa.Column("frozen_policy", postgresql.JSON, nullable=True),
        sa.Column("current_stop", sa.Float, nullable=True),
        sa.Column("current_price", sa.Float, nullable=True),
        sa.Column("milestone_state", postgresql.JSON, nullable=True),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("exit_time", sa.DateTime, nullable=True),
        sa.Column("exit_reason", sa.String(200), nullable=True),
        sa.Column("pnl_realized", sa.Float, nullable=True),
        sa.Column("pnl_unrealized", sa.Float, nullable=True),
        sa.Column("fees_paid", sa.Float, nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_positions_symbol", "positions", ["symbol"])
    op.create_index("ix_positions_state", "positions", ["state"])

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("asset_class", sa.String(10), nullable=False),
        sa.Column("order_type", sa.String(30), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("requested_price", sa.Float, nullable=True),
        sa.Column("fill_price", sa.Float, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("broker_order_id", sa.String(100), nullable=True),
        sa.Column("placed_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("filled_at", sa.DateTime, nullable=True),
        sa.Column("fees", sa.Float, nullable=True, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_orders_symbol", "orders", ["symbol"])
    op.create_index("ix_orders_position_id", "orders", ["position_id"])

    op.create_table(
        "ledger_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_class", sa.String(10), nullable=False, unique=True),
        sa.Column("cash_balance", sa.Float, nullable=False, server_default="0"),
        sa.Column("fees_total", sa.Float, nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("last_reconciled_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_class", sa.String(10), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("balance_after", sa.Float, nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_ledger_entries_asset_class", "ledger_entries", ["asset_class"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("asset_class", sa.String(10), nullable=True),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="SYSTEM"),
        sa.Column("event_data", postgresql.JSON, nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_symbol", "audit_events", ["symbol"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("ledger_entries")
    op.drop_table("ledger_accounts")
    op.drop_table("orders")
    op.drop_table("positions")
    op.drop_table("watchlist_symbols")
