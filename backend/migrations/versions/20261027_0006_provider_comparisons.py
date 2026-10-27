"""Saved HERE vs Google/Grab comparisons and their rows.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE provider_comparisons (
	id UUID NOT NULL,
	aoi VARCHAR(80) NOT NULL,
	dataset_id UUID,
	dataset_filename VARCHAR(255) NOT NULL,
	extract_filename VARCHAR(255) NOT NULL,
	source_filename VARCHAR(255) NOT NULL,
	stats JSONB NOT NULL,
	created_by UUID,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_provider_comparisons PRIMARY KEY (id),
	CONSTRAINT fk_provider_comparisons_dataset_id_customer_datasets FOREIGN KEY(dataset_id) REFERENCES customer_datasets (id) ON DELETE SET NULL,
	CONSTRAINT fk_provider_comparisons_created_by_users FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
)""")
    op.execute("CREATE INDEX ix_provider_comparisons_aoi ON provider_comparisons (aoi)")
    op.execute("""
CREATE TABLE provider_comparison_rows (
	id SERIAL NOT NULL,
	comparison_id UUID NOT NULL,
	kind VARCHAR(16) NOT NULL,
	position INTEGER NOT NULL,
	name VARCHAR(500) NOT NULL,
	here_placeid VARCHAR(120) NOT NULL,
	delete_basis VARCHAR(60) NOT NULL,
	search_text VARCHAR(2000) NOT NULL,
	latitude FLOAT,
	longitude FLOAT,
	data JSONB NOT NULL,
	CONSTRAINT pk_provider_comparison_rows PRIMARY KEY (id),
	CONSTRAINT fk_provider_comparison_rows_comparison_id_provider_comparisons FOREIGN KEY(comparison_id) REFERENCES provider_comparisons (id) ON DELETE CASCADE
)""")
    op.execute("CREATE INDEX ix_provider_rows_comparison_kind ON provider_comparison_rows (comparison_id, kind, position)")


def downgrade():
    op.execute("DROP TABLE provider_comparison_rows")
    op.execute("DROP TABLE provider_comparisons")
