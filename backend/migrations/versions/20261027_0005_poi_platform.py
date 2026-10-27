"""POI discovery, comparison, task, review/QC and delivery workflow tables.

Generated from app/models/platform.py (PostgreSQL dialect) so the DDL matches the models exactly.
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
CREATE TABLE users (
	id UUID NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	display_name VARCHAR(160) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	roles JSONB NOT NULL, 
	aois JSONB NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_users PRIMARY KEY (id), 
	CONSTRAINT uq_users_username UNIQUE (username)
)
    """,
    """
CREATE TABLE user_sessions (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	CONSTRAINT pk_user_sessions PRIMARY KEY (id), 
	CONSTRAINT fk_user_sessions_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	CONSTRAINT uq_user_sessions_token_hash UNIQUE (token_hash)
)
    """,
    """
CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id)
    """,
    """
CREATE TABLE audit_events (
	id SERIAL NOT NULL, 
	actor_id UUID, 
	action VARCHAR(60) NOT NULL, 
	entity VARCHAR(60) NOT NULL, 
	entity_id VARCHAR(80) NOT NULL, 
	details JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_audit_events PRIMARY KEY (id), 
	CONSTRAINT fk_audit_events_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_audit_events_actor_id ON audit_events (actor_id)
    """,
    """
CREATE TABLE source_batches (
	id UUID NOT NULL, 
	aoi VARCHAR(100) NOT NULL, 
	country VARCHAR(3) NOT NULL, 
	source_type VARCHAR(40) NOT NULL, 
	source_name VARCHAR(200) NOT NULL, 
	license_reference TEXT NOT NULL, 
	permitted_use TEXT NOT NULL, 
	collection_method VARCHAR(200) NOT NULL, 
	filename TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	row_count INTEGER NOT NULL, 
	columns JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_source_batches PRIMARY KEY (id), 
	CONSTRAINT uq_source_batches_aoi UNIQUE (aoi, sha256), 
	CONSTRAINT fk_source_batches_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
)
    """,
    """
CREATE TABLE source_observations (
	id SERIAL NOT NULL, 
	batch_id UUID NOT NULL, 
	source_record_id TEXT NOT NULL, 
	name TEXT NOT NULL, 
	alt_names JSONB NOT NULL, 
	category_code VARCHAR(13), 
	category_name TEXT, 
	address TEXT, 
	street_name TEXT, 
	house_number TEXT, 
	unit TEXT, 
	postal_code TEXT, 
	phones JSONB NOT NULL, 
	website TEXT, 
	social_url TEXT, 
	opening_hours TEXT, 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	routing_latitude FLOAT, 
	routing_longitude FLOAT, 
	business_status VARCHAR(24) NOT NULL, 
	observed_on DATE, 
	retrieved_on DATE, 
	source_url TEXT, 
	here_place_id TEXT, 
	raw JSONB NOT NULL, 
	CONSTRAINT pk_source_observations PRIMARY KEY (id), 
	CONSTRAINT uq_source_observations_batch_id UNIQUE (batch_id, source_record_id), 
	CONSTRAINT fk_source_observations_batch_id_source_batches FOREIGN KEY(batch_id) REFERENCES source_batches (id) ON DELETE CASCADE
)
    """,
    """
CREATE INDEX ix_source_observations_batch_id ON source_observations (batch_id)
    """,
    """
CREATE TABLE comparison_runs (
	id UUID NOT NULL, 
	dataset_id UUID NOT NULL, 
	aoi VARCHAR(100) NOT NULL, 
	rules_version VARCHAR(40) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	batch_ids JSONB NOT NULL, 
	stats JSONB NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_comparison_runs PRIMARY KEY (id), 
	CONSTRAINT fk_comparison_runs_dataset_id_customer_datasets FOREIGN KEY(dataset_id) REFERENCES customer_datasets (id) ON DELETE CASCADE, 
	CONSTRAINT fk_comparison_runs_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_comparison_runs_dataset_id ON comparison_runs (dataset_id)
    """,
    """
CREATE INDEX ix_comparison_runs_fingerprint ON comparison_runs (fingerprint)
    """,
    """
CREATE TABLE master_pois (
	id SERIAL NOT NULL, 
	run_id UUID NOT NULL, 
	master_key VARCHAR(64) NOT NULL, 
	jsan_id VARCHAR(40) NOT NULL, 
	name TEXT NOT NULL, 
	category_code VARCHAR(13), 
	latitude FLOAT NOT NULL, 
	longitude FLOAT NOT NULL, 
	observation_ids JSONB NOT NULL, 
	link_reasons JSONB NOT NULL, 
	CONSTRAINT pk_master_pois PRIMARY KEY (id), 
	CONSTRAINT uq_master_pois_run_id UNIQUE (run_id, master_key), 
	CONSTRAINT fk_master_pois_run_id_comparison_runs FOREIGN KEY(run_id) REFERENCES comparison_runs (id) ON DELETE CASCADE
)
    """,
    """
CREATE INDEX ix_master_pois_jsan_id ON master_pois (jsan_id)
    """,
    """
CREATE INDEX ix_master_pois_run_id ON master_pois (run_id)
    """,
    """
CREATE TABLE comparison_results (
	id SERIAL NOT NULL, 
	run_id UUID NOT NULL, 
	result_key VARCHAR(64) NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	outcome VARCHAR(32) NOT NULL, 
	master_id INTEGER, 
	here_poi_id INTEGER, 
	here_place_id TEXT, 
	distance_m FLOAT, 
	band VARCHAR(4), 
	decision_rule VARCHAR(4), 
	priority INTEGER NOT NULL, 
	explanation JSONB NOT NULL, 
	CONSTRAINT pk_comparison_results PRIMARY KEY (id), 
	CONSTRAINT uq_comparison_results_run_id UNIQUE (run_id, result_key), 
	CONSTRAINT fk_comparison_results_run_id_comparison_runs FOREIGN KEY(run_id) REFERENCES comparison_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_comparison_results_master_id_master_pois FOREIGN KEY(master_id) REFERENCES master_pois (id) ON DELETE CASCADE, 
	CONSTRAINT fk_comparison_results_here_poi_id_customer_pois FOREIGN KEY(here_poi_id) REFERENCES customer_pois (id) ON DELETE CASCADE
)
    """,
    """
CREATE INDEX ix_comparison_results_run_outcome ON comparison_results (run_id, outcome)
    """,
    """
CREATE TABLE tasks (
	id SERIAL NOT NULL, 
	task_key VARCHAR(64) NOT NULL, 
	kind VARCHAR(12) NOT NULL, 
	queue VARCHAR(24) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	priority INTEGER NOT NULL, 
	dataset_id UUID NOT NULL, 
	aoi VARCHAR(100) NOT NULL, 
	run_id UUID NOT NULL, 
	result_id INTEGER NOT NULL, 
	result_key VARCHAR(64) NOT NULL, 
	parent_task_id INTEGER, 
	review_id UUID, 
	excluded_user_id UUID, 
	assigned_to UUID, 
	assigned_at TIMESTAMP WITH TIME ZONE, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	rework_count INTEGER NOT NULL, 
	note TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_tasks PRIMARY KEY (id), 
	CONSTRAINT uq_tasks_task_key UNIQUE (task_key), 
	CONSTRAINT fk_tasks_dataset_id_customer_datasets FOREIGN KEY(dataset_id) REFERENCES customer_datasets (id) ON DELETE CASCADE, 
	CONSTRAINT fk_tasks_run_id_comparison_runs FOREIGN KEY(run_id) REFERENCES comparison_runs (id) ON DELETE CASCADE, 
	CONSTRAINT fk_tasks_result_id_comparison_results FOREIGN KEY(result_id) REFERENCES comparison_results (id) ON DELETE CASCADE, 
	CONSTRAINT fk_tasks_parent_task_id_tasks FOREIGN KEY(parent_task_id) REFERENCES tasks (id), 
	CONSTRAINT fk_tasks_excluded_user_id_users FOREIGN KEY(excluded_user_id) REFERENCES users (id), 
	CONSTRAINT fk_tasks_assigned_to_users FOREIGN KEY(assigned_to) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_tasks_assigned_to ON tasks (assigned_to)
    """,
    """
CREATE INDEX ix_tasks_dataset_id ON tasks (dataset_id)
    """,
    """
CREATE INDEX ix_tasks_result_key ON tasks (result_key)
    """,
    """
CREATE INDEX ix_tasks_queue_status ON tasks (queue, status, priority)
    """,
    """
CREATE TABLE task_events (
	id SERIAL NOT NULL, 
	task_id INTEGER NOT NULL, 
	actor_id UUID, 
	event VARCHAR(30) NOT NULL, 
	from_status VARCHAR(16), 
	to_status VARCHAR(16), 
	details JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_task_events PRIMARY KEY (id), 
	CONSTRAINT fk_task_events_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	CONSTRAINT fk_task_events_actor_id_users FOREIGN KEY(actor_id) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_task_events_task_id ON task_events (task_id)
    """,
    """
CREATE TABLE review_decisions (
	id UUID NOT NULL, 
	task_id INTEGER NOT NULL, 
	result_id INTEGER NOT NULL, 
	result_key VARCHAR(64) NOT NULL, 
	reviewer_id UUID NOT NULL, 
	decision VARCHAR(16) NOT NULL, 
	here_place_id TEXT, 
	attributes JSONB NOT NULL, 
	evidence JSONB NOT NULL, 
	verification_date DATE, 
	remarks TEXT NOT NULL, 
	delete_reason VARCHAR(40), 
	duplicate_of TEXT, 
	field_issue TEXT, 
	confidence_score FLOAT, 
	rule_check JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_review_decisions PRIMARY KEY (id), 
	CONSTRAINT fk_review_decisions_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	CONSTRAINT fk_review_decisions_result_id_comparison_results FOREIGN KEY(result_id) REFERENCES comparison_results (id) ON DELETE CASCADE, 
	CONSTRAINT fk_review_decisions_reviewer_id_users FOREIGN KEY(reviewer_id) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_review_decisions_result_key ON review_decisions (result_key)
    """,
    """
CREATE INDEX ix_review_decisions_task_id ON review_decisions (task_id)
    """,
    """
CREATE TABLE qc_decisions (
	id UUID NOT NULL, 
	task_id INTEGER NOT NULL, 
	review_id UUID NOT NULL, 
	qc_user_id UUID NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	reclassified_to VARCHAR(16), 
	remarks TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_qc_decisions PRIMARY KEY (id), 
	CONSTRAINT fk_qc_decisions_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	CONSTRAINT fk_qc_decisions_review_id_review_decisions FOREIGN KEY(review_id) REFERENCES review_decisions (id) ON DELETE CASCADE, 
	CONSTRAINT fk_qc_decisions_qc_user_id_users FOREIGN KEY(qc_user_id) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_qc_decisions_task_id ON qc_decisions (task_id)
    """,
    """
CREATE INDEX ix_qc_decisions_review_id ON qc_decisions (review_id)
    """,
    """
CREATE TABLE field_observations (
	id UUID NOT NULL, 
	task_id INTEGER NOT NULL, 
	result_key VARCHAR(64) NOT NULL, 
	verifier_id UUID NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	data JSONB NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_field_observations PRIMARY KEY (id), 
	CONSTRAINT fk_field_observations_task_id_tasks FOREIGN KEY(task_id) REFERENCES tasks (id) ON DELETE CASCADE, 
	CONSTRAINT fk_field_observations_verifier_id_users FOREIGN KEY(verifier_id) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_field_observations_task_id ON field_observations (task_id)
    """,
    """
CREATE INDEX ix_field_observations_result_key ON field_observations (result_key)
    """,
    """
CREATE TABLE approved_records (
	id SERIAL NOT NULL, 
	dataset_id UUID NOT NULL, 
	result_key VARCHAR(64) NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	review_id UUID NOT NULL, 
	qc_id UUID NOT NULL, 
	approved_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_approved_records PRIMARY KEY (id), 
	CONSTRAINT uq_approved_records_dataset_id UNIQUE (dataset_id, result_key), 
	CONSTRAINT fk_approved_records_dataset_id_customer_datasets FOREIGN KEY(dataset_id) REFERENCES customer_datasets (id) ON DELETE CASCADE, 
	CONSTRAINT fk_approved_records_review_id_review_decisions FOREIGN KEY(review_id) REFERENCES review_decisions (id), 
	CONSTRAINT fk_approved_records_qc_id_qc_decisions FOREIGN KEY(qc_id) REFERENCES qc_decisions (id)
)
    """,
    """
CREATE INDEX ix_approved_records_dataset_id ON approved_records (dataset_id)
    """,
    """
CREATE TABLE delivery_snapshots (
	id UUID NOT NULL, 
	dataset_id UUID NOT NULL, 
	aoi VARCHAR(100) NOT NULL, 
	version VARCHAR(16) NOT NULL, 
	created_by UUID NOT NULL, 
	checks JSONB NOT NULL, 
	counts JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_delivery_snapshots PRIMARY KEY (id), 
	CONSTRAINT fk_delivery_snapshots_dataset_id_customer_datasets FOREIGN KEY(dataset_id) REFERENCES customer_datasets (id) ON DELETE CASCADE, 
	CONSTRAINT fk_delivery_snapshots_created_by_users FOREIGN KEY(created_by) REFERENCES users (id)
)
    """,
    """
CREATE INDEX ix_delivery_snapshots_dataset_id ON delivery_snapshots (dataset_id)
    """,
    """
CREATE TABLE delivery_files (
	id SERIAL NOT NULL, 
	snapshot_id UUID NOT NULL, 
	kind VARCHAR(24) NOT NULL, 
	filename TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	row_count INTEGER NOT NULL, 
	customer_facing BOOLEAN NOT NULL, 
	content BYTEA NOT NULL, 
	CONSTRAINT pk_delivery_files PRIMARY KEY (id), 
	CONSTRAINT fk_delivery_files_snapshot_id_delivery_snapshots FOREIGN KEY(snapshot_id) REFERENCES delivery_snapshots (id) ON DELETE CASCADE
)
    """,
    """
CREATE INDEX ix_delivery_files_snapshot_id ON delivery_files (snapshot_id)
    """,
    """
ALTER TABLE tasks ADD CONSTRAINT fk_tasks_review_id_review_decisions FOREIGN KEY(review_id) REFERENCES review_decisions (id)
    """,
]

TABLES = ['delivery_files', 'delivery_snapshots', 'approved_records', 'field_observations', 'qc_decisions', 'review_decisions', 'task_events', 'tasks', 'comparison_results', 'master_pois', 'comparison_runs', 'source_observations', 'source_batches', 'audit_events', 'user_sessions', 'users']


def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade():
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS fk_tasks_review_id_review_decisions")
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
