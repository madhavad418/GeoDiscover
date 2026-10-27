"""Persist internal POC baseline preflight reports, not provider data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('poc_preflight_runs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('dataset_id', sa.Uuid(), sa.ForeignKey('customer_datasets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('report', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_poc_preflight_runs_dataset_id', 'poc_preflight_runs', ['dataset_id'])


def downgrade():
    op.drop_table('poc_preflight_runs')
