"""create bot_strategy_decisions table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bot_strategy_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('evaluated_at', sa.DateTime(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=True),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('normalized_symbol', sa.String(length=50), nullable=True),
        sa.Column('asset_class', sa.String(length=10), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('scan_id', sa.String(length=100), nullable=True),
        sa.Column('schema_version', sa.String(length=50), nullable=True),
        sa.Column('regime', sa.String(length=50), nullable=True),
        sa.Column('ai_hint_present', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('ai_hint_strategy', sa.String(length=50), nullable=True),
        sa.Column('ai_hint_confidence', sa.Float(), nullable=True),
        sa.Column('ai_hint_bias_applied', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('ai_hint_bias_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('bot_selected_strategy', sa.String(length=50), nullable=True),
        sa.Column('bot_selected_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('ai_hint_agreement', sa.Boolean(), nullable=True),
        sa.Column('bias_changed_outcome', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('watchlist_symbol_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('watchlist_upload_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('trade_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('position_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('evaluated_strategy_scores', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('rejected_strategies', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('feature_scores', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('decision_context', postgresql.JSONB(), nullable=False, server_default='{}'),
    )
    op.create_index('ix_bot_strategy_decisions_symbol_evaluated_at', 'bot_strategy_decisions', ['symbol', 'evaluated_at'])
    op.create_index('ix_bot_strategy_decisions_asset_class_evaluated_at', 'bot_strategy_decisions', ['asset_class', 'evaluated_at'])
    op.create_index('ix_bot_strategy_decisions_ai_hint_agreement', 'bot_strategy_decisions', ['ai_hint_agreement', 'evaluated_at'])
    op.create_index('ix_bot_strategy_decisions_bot_selected_strategy', 'bot_strategy_decisions', ['bot_selected_strategy', 'evaluated_at'])
    op.create_index('ix_bot_strategy_decisions_ai_hint_strategy', 'bot_strategy_decisions', ['ai_hint_strategy', 'evaluated_at'])


def downgrade():
    op.drop_index('ix_bot_strategy_decisions_ai_hint_strategy', table_name='bot_strategy_decisions')
    op.drop_index('ix_bot_strategy_decisions_bot_selected_strategy', table_name='bot_strategy_decisions')
    op.drop_index('ix_bot_strategy_decisions_ai_hint_agreement', table_name='bot_strategy_decisions')
    op.drop_index('ix_bot_strategy_decisions_asset_class_evaluated_at', table_name='bot_strategy_decisions')
    op.drop_index('ix_bot_strategy_decisions_symbol_evaluated_at', table_name='bot_strategy_decisions')
    op.drop_table('bot_strategy_decisions')
