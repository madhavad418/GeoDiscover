"""POI discovery, comparison, review/QC and delivery workflow.

Types are portable (JSONB on PostgreSQL, JSON elsewhere) so the workflow can be tested on SQLite.
"""
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

Json = JSON().with_variant(JSONB(), "postgresql")


def _ts(**kw):
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kw)


# ---------- Identity & access ----------
class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    roles: Mapped[list] = mapped_column(Json, default=list)
    aois: Mapped[list] = mapped_column(Json, default=list)  # empty = all AOIs
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _ts()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = _ts()


# ---------- Permitted source observations ----------
class SourceBatch(Base):
    __tablename__ = "source_batches"
    __table_args__ = (UniqueConstraint("aoi", "sha256"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    aoi: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(3))
    source_type: Mapped[str] = mapped_column(String(40))
    source_name: Mapped[str] = mapped_column(String(200))
    license_reference: Mapped[str] = mapped_column(Text)
    permitted_use: Mapped[str] = mapped_column(Text)
    collection_method: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer)
    columns: Mapped[list] = mapped_column(Json)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts()


class SourceObservation(Base):
    __tablename__ = "source_observations"
    __table_args__ = (UniqueConstraint("batch_id", "source_record_id"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("source_batches.id", ondelete="CASCADE"), index=True)
    source_record_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    alt_names: Mapped[list] = mapped_column(Json, default=list)
    category_code: Mapped[str | None] = mapped_column(String(13))
    category_name: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    street_name: Mapped[str | None] = mapped_column(Text)
    house_number: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    phones: Mapped[list] = mapped_column(Json, default=list)
    website: Mapped[str | None] = mapped_column(Text)
    social_url: Mapped[str | None] = mapped_column(Text)
    opening_hours: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    routing_latitude: Mapped[float | None] = mapped_column(Float)
    routing_longitude: Mapped[float | None] = mapped_column(Float)
    business_status: Mapped[str] = mapped_column(String(24), default="unknown")
    observed_on: Mapped[date | None] = mapped_column(Date)
    retrieved_on: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)
    here_place_id: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(Json)


# ---------- Comparison ----------
class ComparisonRun(Base):
    __tablename__ = "comparison_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("customer_datasets.id", ondelete="CASCADE"), index=True)
    aoi: Mapped[str] = mapped_column(String(100))
    rules_version: Mapped[str] = mapped_column(String(40))
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    batch_ids: Mapped[list] = mapped_column(Json)
    stats: Mapped[dict] = mapped_column(Json, default=dict)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _ts()


class MasterPoi(Base):
    __tablename__ = "master_pois"
    __table_args__ = (UniqueConstraint("run_id", "master_key"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("comparison_runs.id", ondelete="CASCADE"), index=True)
    master_key: Mapped[str] = mapped_column(String(64))
    jsan_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(Text)
    category_code: Mapped[str | None] = mapped_column(String(13))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    observation_ids: Mapped[list] = mapped_column(Json)
    link_reasons: Mapped[list] = mapped_column(Json, default=list)


class ComparisonResult(Base):
    __tablename__ = "comparison_results"
    __table_args__ = (UniqueConstraint("run_id", "result_key"), Index("ix_comparison_results_run_outcome", "run_id", "outcome"))
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("comparison_runs.id", ondelete="CASCADE"))
    result_key: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("master_pois.id", ondelete="CASCADE"))
    here_poi_id: Mapped[int | None] = mapped_column(ForeignKey("customer_pois.id", ondelete="CASCADE"))
    here_place_id: Mapped[str | None] = mapped_column(Text)
    distance_m: Mapped[float | None] = mapped_column(Float)
    band: Mapped[str | None] = mapped_column(String(4))
    decision_rule: Mapped[str | None] = mapped_column(String(4))
    priority: Mapped[int] = mapped_column(Integer, default=3)
    explanation: Mapped[dict] = mapped_column(Json)


# ---------- Tasks ----------
class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_queue_status", "queue", "status", "priority"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(12))  # review | qc | field
    queue: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="open")
    priority: Mapped[int] = mapped_column(Integer, default=3)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("customer_datasets.id", ondelete="CASCADE"), index=True)
    aoi: Mapped[str] = mapped_column(String(100))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("comparison_runs.id", ondelete="CASCADE"))
    result_id: Mapped[int] = mapped_column(ForeignKey("comparison_results.id", ondelete="CASCADE"))
    result_key: Mapped[str] = mapped_column(String(64), index=True)
    parent_task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"))
    review_id: Mapped[UUID | None] = mapped_column(ForeignKey("review_decisions.id", use_alter=True))
    excluded_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _ts()


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    event: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str | None] = mapped_column(String(16))
    details: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = _ts()


# ---------- Decisions ----------
class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("comparison_results.id", ondelete="CASCADE"))
    result_key: Mapped[str] = mapped_column(String(64), index=True)
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(16))
    # HERE record the decision applies to (chosen by the reviewer for fallout results with several candidates).
    here_place_id: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(Json)
    evidence: Mapped[list] = mapped_column(Json)
    verification_date: Mapped[date | None] = mapped_column(Date)
    remarks: Mapped[str] = mapped_column(Text, default="")
    delete_reason: Mapped[str | None] = mapped_column(String(40))
    duplicate_of: Mapped[str | None] = mapped_column(Text)
    field_issue: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    rule_check: Mapped[dict] = mapped_column(Json, default=dict)
    created_at: Mapped[datetime] = _ts()


class QcDecision(Base):
    __tablename__ = "qc_decisions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    review_id: Mapped[UUID] = mapped_column(ForeignKey("review_decisions.id", ondelete="CASCADE"), index=True)
    qc_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(16))
    reclassified_to: Mapped[str | None] = mapped_column(String(16))
    remarks: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _ts()


class FieldObservation(Base):
    __tablename__ = "field_observations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    result_key: Mapped[str] = mapped_column(String(64), index=True)
    verifier_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24))
    data: Mapped[dict] = mapped_column(Json)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()


class ApprovedRecord(Base):
    """One QC-approved final decision per baseline record identity, the input to delivery."""
    __tablename__ = "approved_records"
    __table_args__ = (UniqueConstraint("dataset_id", "result_key"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("customer_datasets.id", ondelete="CASCADE"), index=True)
    result_key: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    review_id: Mapped[UUID] = mapped_column(ForeignKey("review_decisions.id"))
    qc_id: Mapped[UUID] = mapped_column(ForeignKey("qc_decisions.id"))
    approved_at: Mapped[datetime] = _ts()


# ---------- Delivery ----------
class DeliverySnapshot(Base):
    __tablename__ = "delivery_snapshots"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("customer_datasets.id", ondelete="CASCADE"), index=True)
    aoi: Mapped[str] = mapped_column(String(100))
    version: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    checks: Mapped[list] = mapped_column(Json)
    counts: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = _ts()


class DeliveryFile(Base):
    __tablename__ = "delivery_files"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("delivery_snapshots.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    filename: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    customer_facing: Mapped[bool] = mapped_column(Boolean, default=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
