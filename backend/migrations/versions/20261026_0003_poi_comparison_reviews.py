"""Persist decisions on HERE versus provider POI comparison proposals."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE poi_comparison_reviews (
            id UUID PRIMARY KEY,
            dataset_id UUID NOT NULL REFERENCES customer_datasets(id) ON DELETE CASCADE,
            provider VARCHAR(16) NOT NULL,
            record_key VARCHAR(64) NOT NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            note TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_poi_comparison_reviews_dataset_id UNIQUE (dataset_id, provider, record_key),
            CONSTRAINT ck_poi_comparison_reviews_status CHECK (status IN ('pending', 'approved', 'rejected')),
            CONSTRAINT ck_poi_comparison_reviews_provider CHECK (provider IN ('google', 'apple', 'grab'))
        )
    """)
    op.execute("CREATE INDEX ix_poi_comparison_reviews_dataset_status ON poi_comparison_reviews(dataset_id, status)")


def downgrade():
    op.drop_table("poi_comparison_reviews")
