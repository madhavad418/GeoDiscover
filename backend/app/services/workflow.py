"""Task generation, allocation and state transitions (consolidated requirements §4, §6, §7)."""
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from ..auth import now
from ..models.platform import (
    ApprovedRecord, ComparisonResult, FieldObservation, QcDecision, ReviewDecision, Task, TaskEvent, User,
)
from .matching import sha

REVIEW_QUEUES = {
    "potential_new": "review_new", "potential_update": "review_update", "potential_delete": "review_delete",
    "verification_required": "review_verify", "fallout_review": "review_fallout", "no_change": "review_no_change",
}
QC_QUEUES = {"new": "qc_new", "update": "qc_update", "delete": "qc_delete", "no_change": "qc_no_change"}
QUEUE_LABELS = {
    "review_new": "Review · Potential NEW", "review_update": "Review · Potential UPDATE",
    "review_delete": "Review · Potential DELETE", "review_verify": "Review · Verification required",
    "review_fallout": "Review · Fallout", "review_no_change": "Review · No change", "rework": "Returned / Rework",
    "qc_new": "NEW QC", "qc_update": "UPDATE QC", "qc_delete": "DELETE QC", "qc_no_change": "NO CHANGE QC",
    "qc_fallout": "Fallout / Exception QC", "field": "Field verification", "escalated": "Escalated / Hold",
}
QUEUE_ROLES = {q: {"reviewer"} for q in REVIEW_QUEUES.values()} | {
    "rework": {"reviewer"}, "field": {"field_verifier"}, "escalated": {"qc_lead"},
    **{q: {"qc_analyst", "qc_lead"} for q in [*QC_QUEUES.values(), "qc_fallout"]},
}
ACTIVE = ("assigned", "in_progress")
DEFAULT_BATCH, MAX_OPEN_PER_USER = 10, 30


def log(db: Session, task: Task, actor: User | None, event: str, to_status: str | None = None, **details):
    db.add(TaskEvent(task_id=task.id, actor_id=actor.id if actor else None, event=event, from_status=task.status,
                     to_status=to_status or task.status, details=details))
    if to_status:
        task.status = to_status


def eligible_queues(user: User) -> list[str]:
    return [q for q, roles in QUEUE_ROLES.items() if roles & set(user.roles)]


# Default: findings backed by a permitted source. VERIFICATION REQUIRED (HERE POIs no source observed) can be
# thousands of records, so those tasks are created only when asked for, separately.
SOURCE_BACKED = ("potential_new", "potential_update", "potential_delete", "fallout_review")


def generate_review_tasks(db: Session, run, include=SOURCE_BACKED, actor=None):
    """Create one review task per actionable result. Idempotent: the key covers the finding's content, so a
    re-run with unchanged inputs creates nothing; an unclaimed task for a changed finding is superseded."""
    results = db.scalars(select(ComparisonResult).where(ComparisonResult.run_id == run.id,
                                                        ComparisonResult.outcome.in_(include))).all()
    keys = {sha(r.result_key, "review", r.content_hash): r for r in results}
    existing = set(db.scalars(select(Task.task_key).where(Task.task_key.in_(keys))).all()) if keys else set()
    created = 0
    open_by_result = {}
    if results:
        for t in db.scalars(select(Task).where(Task.kind == "review", Task.status == "open",
                                                Task.result_key.in_({r.result_key for r in results}))):
            open_by_result.setdefault(t.result_key, []).append(t)
    superseded = 0
    for key, r in keys.items():
        if key in existing:
            continue
        for old in open_by_result.get(r.result_key, []):
            if old.task_key != key:
                log(db, old, actor, "superseded", "superseded", by_run=str(run.id))
                superseded += 1
        task = Task(task_key=key, kind="review", queue=REVIEW_QUEUES[r.outcome], status="open", priority=r.priority,
                    dataset_id=run.dataset_id, aoi=run.aoi, run_id=run.id, result_id=r.id, result_key=r.result_key)
        db.add(task)
        db.flush()
        log(db, task, actor, "created", "open", outcome=r.outcome)
        created += 1
    return {"created": created, "already_present": len(existing), "superseded": superseded}


def _independent(user_id):
    """The user has not reviewed or field-verified this record (QC must be someone else)."""
    reviewed = exists().where(ReviewDecision.result_key == Task.result_key, ReviewDecision.reviewer_id == user_id)
    fielded = exists().where(FieldObservation.result_key == Task.result_key, FieldObservation.verifier_id == user_id)
    return ~reviewed & ~fielded


def is_independent(db: Session, task: Task, user: User) -> bool:
    return not db.scalar(select(func.count()).select_from(ReviewDecision).where(
        ReviewDecision.result_key == task.result_key, ReviewDecision.reviewer_id == user.id)) and \
        not db.scalar(select(func.count()).select_from(FieldObservation).where(
            FieldObservation.result_key == task.result_key, FieldObservation.verifier_id == user.id))


def claim(db: Session, user: User, limit: int = DEFAULT_BATCH, queues: list[str] | None = None):
    """Get Tasks: keep the user's in-progress work and top up to `limit` from eligible open queues.

    Rows are locked with FOR UPDATE SKIP LOCKED, so concurrent claims never receive the same task.
    """
    mine = db.scalar(select(func.count()).select_from(Task).where(Task.assigned_to == user.id, Task.status.in_(ACTIVE)))
    room = max(0, min(limit, MAX_OPEN_PER_USER - mine))
    allowed = [q for q in eligible_queues(user) if not queues or q in queues]
    claimed = []
    if room and allowed:
        query = select(Task).where(Task.status == "open", Task.queue.in_(allowed))
        if user.aois:
            query = query.where(Task.aoi.in_(user.aois))
        if {q for q in allowed if q.startswith("qc_") or q == "escalated"}:
            query = query.where((~Task.queue.like("qc_%") & (Task.queue != "escalated")) | _independent(user.id))
        query = query.order_by(Task.priority, Task.created_at, Task.id).limit(room).with_for_update(skip_locked=True)
        for task in db.scalars(query):
            task.assigned_to, task.assigned_at = user.id, now()
            log(db, task, user, "assigned", "assigned", via="get_tasks")
            claimed.append(task)
    return claimed, mine


def assign(db: Session, task: Task, assignee: User, actor: User, reason: str):
    if task.status in ("completed", "cancelled", "superseded"):
        raise ValueError("This task is closed.")
    if not QUEUE_ROLES[task.queue] & set(assignee.roles):
        raise ValueError(f"{assignee.display_name} doesn't have a role for {QUEUE_LABELS[task.queue]}.")
    if (task.queue.startswith("qc_") or task.queue == "escalated") and not is_independent(db, task, assignee):
        raise ValueError("QC must be independent: this user reviewed or field-verified the record.")
    previous = task.assigned_to
    task.assigned_to, task.assigned_at = assignee.id, now()
    task.started_at = None
    log(db, task, actor, "reassigned", "assigned", from_user=str(previous) if previous else None,
        to_user=str(assignee.id), reason=reason)


def start(db: Session, task: Task, user: User):
    if task.status == "assigned":
        task.started_at = task.started_at or now()
        log(db, task, user, "started", "in_progress")


def complete(db: Session, task: Task, user: User, event: str, **details):
    task.completed_at = now()
    log(db, task, user, event, "completed", **details)


def spawn(db: Session, parent: Task, kind: str, queue: str, key: str, actor: User, assigned_to=None,
          review_id=None, note="", priority=None):
    """Create a follow-up task (QC, rework, field) for the same record; idempotent on `key`."""
    existing = db.scalar(select(Task).where(Task.task_key == key))
    if existing:
        return existing
    task = Task(task_key=key, kind=kind, queue=queue, status="assigned" if assigned_to else "open",
                priority=parent.priority if priority is None else priority, dataset_id=parent.dataset_id, aoi=parent.aoi,
                run_id=parent.run_id, result_id=parent.result_id, result_key=parent.result_key, parent_task_id=parent.id,
                review_id=review_id, assigned_to=assigned_to, assigned_at=now() if assigned_to else None,
                rework_count=parent.rework_count + (1 if queue == "rework" else 0), note=note)
    db.add(task)
    db.flush()
    log(db, task, actor, "created", task.status, parent=parent.id, note=note)
    return task


def approve(db: Session, task: Task, review: ReviewDecision, qc: QcDecision):
    """Record the QC-approved final decision for delivery (one per baseline record identity)."""
    record = db.scalar(select(ApprovedRecord).where(ApprovedRecord.dataset_id == task.dataset_id,
                                                     ApprovedRecord.result_key == task.result_key))
    if record:
        record.action, record.review_id, record.qc_id, record.approved_at = review.decision, review.id, qc.id, now()
    else:
        db.add(ApprovedRecord(dataset_id=task.dataset_id, result_key=task.result_key, action=review.decision,
                              review_id=review.id, qc_id=qc.id))


def withdraw_approval(db: Session, task: Task):
    db.execute(update(ApprovedRecord).where(ApprovedRecord.dataset_id == task.dataset_id,
                                            ApprovedRecord.result_key == task.result_key).values(action="withdrawn"))
