"""Persistent customer baseline imports with WGS84 PostGIS points."""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    available = op.get_bind().exec_driver_sql(
        "SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'").scalar()
    if not available:
        raise RuntimeError("PostGIS is not installed on this PostgreSQL server. "
                           "Use a PostGIS-enabled database (e.g. Railway's PostGIS template).")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("""
        CREATE TABLE customer_datasets (
            id UUID PRIMARY KEY,
            filename TEXT NOT NULL,
            customer VARCHAR(100) NOT NULL,
            aoi VARCHAR(100) NOT NULL,
            country VARCHAR(3) NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            row_count INTEGER NOT NULL,
            columns JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_customer_datasets_aoi UNIQUE (aoi, sha256)
        )
    """)
    op.execute("""
        CREATE TABLE customer_pois (
            id SERIAL PRIMARY KEY,
            dataset_id UUID NOT NULL REFERENCES customer_datasets(id) ON DELETE CASCADE,
            place_id TEXT NOT NULL,
            name TEXT NOT NULL,
            category_code TEXT,
            category_name TEXT,
            country VARCHAR(3) NOT NULL,
            address TEXT,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            routing_latitude DOUBLE PRECISION,
            routing_longitude DOUBLE PRECISION,
            display_point geometry(Point,4326) NOT NULL,
            routing_point geometry(Point,4326),
            raw JSONB NOT NULL,
            CONSTRAINT uq_customer_pois_dataset_id UNIQUE (dataset_id, place_id)
        )
    """)
    op.execute("CREATE INDEX ix_customer_pois_display_point ON customer_pois USING gist(display_point)")
    op.execute("CREATE INDEX ix_customer_pois_routing_point ON customer_pois USING gist(routing_point)")
    op.execute("CREATE INDEX ix_customer_pois_dataset_category ON customer_pois(dataset_id, category_name)")


def downgrade():
    op.drop_table("customer_pois")
    op.drop_table("customer_datasets")
    # PostGIS may be shared by other tables; leave the extension installed.
