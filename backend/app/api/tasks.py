from datetime import date, datetime
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import ROLES, aware, can_access_aoi, current_user, now, require_roles
from ..models.customer import CustomerPoi
from ..models.platform import (
    ApprovedRecord, ComparisonResult, FieldObservation, MasterPoi, QcDecision, ReviewDecision, SourceBatch,
    SourceObservation, Task, TaskEvent, User,
)
from ..services import workflow as wf
from ..services.aoi import contains
from ..services.matching import OUTCOMES, haversine_m
from ..services.reference import categories
from ..services.review_rules import ATTRIBUTES, DELETE_REASONS, EVIDENCE_TYPES, validate_decision
from .customer import storage
from .sources import batch_dict, observation_dict

router = APIRouter(prefix="/tasks", tags=["tasks, review & QC"])
SUPERVISORS = {"qc_lead", "ops_manager"}
FIELD_STATUSES = ("existing", "temporarily_closed", "permanently_closed", "moved", "not_found")


def task_dict(t: Task, users=None):
    users = users or {}
    return {"id": t.id, "ref": f"T-{t.id:06d}", "kind": t.kind, "queue": t.queue, "queue_label": wf.QUEUE_LABELS.get(t.queue, t.queue),
            "status": t.status, "priority": t.priority, "aoi": t.aoi, "dataset_id": str(t.dataset_id), "run_id": str(t.run_id),
            "result_id": t.result_id, "assigned_to": str(t.assigned_to) if t.assigned_to else None,
            "assignee": users.get(t.assigned_to), "assigned_at": _iso(t.assigned_at), "started_at": _iso(t.started_at),
            "completed_at": _iso(t.completed_at), "created_at": _iso(t.created_at), "rework_count": t.rework_count,
            "parent_task_id": t.parent_task_id, "review_id": str(t.review_id) if t.review_id else None, "note": t.note}


def _iso(value):
    return aware(value).isoformat() if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else value


def _names(db):
    return {u.id: u.display_name for u in db.scalars(select(User))}


def _task(db, task_id, user, *, for_update=False) -> Task:
    query = select(Task).where(Task.id == task_id)
    task = db.scalar(query.with_for_update() if for_update else query)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.assigned_to != user.id and not SUPERVISORS & set(user.roles):
        raise HTTPException(403, "This task is assigned to someone else.")
    if not can_access_aoi(user, task.aoi):
        raise HTTPException(403, "This task is outside your assigned areas.")
    return task


def _require_mine(task: Task, user: User, kinds, statuses=wf.ACTIVE):
    if task.kind not in kinds:
        raise HTTPException(409, "This action doesn't apply to this task type.")
    if task.assigned_to != user.id:
        raise HTTPException(403, "Only the assigned user can complete this task.")
    if task.status not in statuses:
        raise HTTPException(409, f"This task is {task.status}.")


# ---------- Work queues ----------
@router.get("/summary")
def summary(db: Session = Depends(storage), user: User = Depends(current_user)):
    queues = wf.eligible_queues(user)
    query = select(Task.queue, func.count()).where(Task.status == "open", Task.queue.in_(queues))
    if user.aois:
        query = query.where(Task.aoi.in_(user.aois))
    open_counts = dict(db.execute(query.group_by(Task.queue)).all())
    mine = db.scalars(select(Task).where(Task.assigned_to == user.id, Task.status.in_((*wf.ACTIVE, "on_hold")))
                      .order_by(Task.priority, Task.id)).all()
    done_today = db.scalar(select(func.count()).select_from(TaskEvent).where(
        TaskEvent.actor_id == user.id, TaskEvent.to_status == "completed",
        TaskEvent.created_at >= datetime.combine(date.today(), datetime.min.time())))
    return {"user": {"display_name": user.display_name, "roles": {r: ROLES[r] for r in user.roles}, "aois": user.aois},
            "queues": [{"id": q, "label": wf.QUEUE_LABELS[q], "open": open_counts.get(q, 0)} for q in queues],
            "assignments": [task_dict(t) for t in mine], "completed_today": done_today,
            "batch_size": wf.DEFAULT_BATCH, "max_open": wf.MAX_OPEN_PER_USER}


class ClaimRequest(BaseModel):
    limit: int = Field(wf.DEFAULT_BATCH, ge=1, le=50)
    queues: list[str] | None = None


@router.post("/claim")
def claim(body: ClaimRequest, db: Session = Depends(storage), user: User = Depends(current_user)):
    claimed, kept = wf.claim(db, user, body.limit, body.queues)
    db.commit()
    return {"claimed": [task_dict(t) for t in claimed], "kept_in_progress": kept}


@router.get("")
def list_tasks(queue: str | None = None, status: str | None = None, assigned_to: UUID | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
               db: Session = Depends(storage), user: User = Depends(require_roles(*SUPERVISORS))):
    conditions = []
    if queue:
        conditions.append(Task.queue == queue)
    if status:
        conditions.append(Task.status == status)
    if assigned_to:
        conditions.append(Task.assigned_to == assigned_to)
    if user.aois:
        conditions.append(Task.aoi.in_(user.aois))
    total = db.scalar(select(func.count()).select_from(Task).where(*conditions))
    rows = db.scalars(select(Task).where(*conditions).order_by(Task.priority, Task.id).offset((page - 1) * page_size).limit(page_size))
    names = _names(db)
    return {"total": total, "tasks": [task_dict(t, names) for t in rows]}


# ---------- Task context (the evidence-based review window) ----------
def reference_links(lat, lon, name):
    """Map-provider links open the provider's own viewer; nothing is fetched or stored from them."""
    q = quote(f"{name} {lat},{lon}" if name else f"{lat},{lon}")
    return [
        {"label": "Google Maps (search here)", "url": f"https://www.google.com/maps/search/?api=1&query={q}"},
        {"label": "Google Street View", "url": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"},
        {"label": "OpenStreetMap", "url": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}"},
    ]


def _here_dict(p: CustomerPoi):
    return {"id": p.id, "place_id": p.place_id, "name": p.name, "category_code": p.category_code, "category_name": p.category_name,
            "address": p.address, "latitude": p.latitude, "longitude": p.longitude, "routing_latitude": p.routing_latitude,
            "routing_longitude": p.routing_longitude, "raw": p.raw}


HERE_ATTRIBUTE_SOURCES = {
    "name": "name1", "transliteration": "name2", "category_code": "primarycategory", "poi_status": "status",
    "house_number": "hno", "street_name": "streetname", "address": "upaddress", "postal_code": "postalcode",
    "admin2": "admin2", "admin3": "admin3", "admin4": "admin4", "admin5": "admin5", "phone": "phone_numbers",
    "mobile": "mobile_numbers", "tollfree": "tollfree_numbers", "email": "email", "website": "webaddress",
    "opening_hours": "opening_hours", "chain_name": "chainname",
}
OBS_ATTRIBUTE_SOURCES = {
    "name": "name", "category_code": "category_code", "house_number": "house_number", "street_name": "street_name",
    "address": "address", "unit": "unit", "postal_code": "postal_code", "website": "website", "opening_hours": "opening_hours",
}


def attribute_grid(here, observations):
    """HERE value, discovered values (with source) and a default final value for every attribute."""
    grid = {}
    for field, label in ATTRIBUTES.items():
        if field in ("latitude", "longitude", "routing_latitude", "routing_longitude"):
            here_value = (here or {}).get(field)
        else:
            here_value = ((here or {}).get("raw") or {}).get(HERE_ATTRIBUTE_SOURCES.get(field, ""), None) if here else None
        observed = []
        for o in observations:
            value = o.get(OBS_ATTRIBUTE_SOURCES[field]) if field in OBS_ATTRIBUTE_SOURCES else None
            if field == "phone" and o.get("phones"):
                value = ", ".join(o["phones"])
            if field in ("latitude", "longitude", "routing_latitude", "routing_longitude"):
                value = o.get(field)
            if field == "poi_status" and o.get("business_status") not in (None, "unknown"):
                value = o["business_status"]
            if value not in (None, ""):
                observed.append({"value": value, "observation_id": o["id"], "source": o["source_name"]})
        grid[field] = {"label": label, "here": here_value, "observed": observed,
                       "default": here_value if here_value not in (None, "") else (observed[0]["value"] if observed else None)}
    return grid


@router.get("/{task_id}")
def task_context(task_id: int, db: Session = Depends(storage), user: User = Depends(current_user)):
    task = _task(db, task_id, user)
    result = db.get(ComparisonResult, task.result_id)
    explanation = result.explanation
    here = db.get(CustomerPoi, result.here_poi_id) if result.here_poi_id else None
    master = db.get(MasterPoi, result.master_id) if result.master_id else None
    observations = []
    if master:
        rows = db.execute(select(SourceObservation, SourceBatch).join(SourceBatch, SourceBatch.id == SourceObservation.batch_id)
                          .where(SourceObservation.id.in_(master.observation_ids))).all()
        for o, b in rows:
            observations.append(observation_dict(o) | {"source_name": b.source_name, "source": batch_dict(b)})
    focus = (master.latitude, master.longitude) if master else (here.latitude, here.longitude)
    nearby = []
    for p in db.scalars(select(CustomerPoi).where(
            CustomerPoi.dataset_id == task.dataset_id,
            CustomerPoi.latitude.between(focus[0] - 0.0012, focus[0] + 0.0012),
            CustomerPoi.longitude.between(focus[1] - 0.0012, focus[1] + 0.0012))):
        d = haversine_m(focus[0], focus[1], p.latitude, p.longitude)
        if d <= 120 and (not here or p.id != here.id):
            nearby.append({"place_id": p.place_id, "name": p.name, "category_name": p.category_name,
                           "latitude": p.latitude, "longitude": p.longitude, "distance_m": round(d, 1)})
    nearby.sort(key=lambda n: n["distance_m"])
    names = _names(db)
    reviews = db.scalars(select(ReviewDecision).where(ReviewDecision.result_key == task.result_key).order_by(ReviewDecision.created_at)).all()
    qcs = db.scalars(select(QcDecision).where(QcDecision.review_id.in_([r.id for r in reviews])).order_by(QcDecision.created_at)).all() if reviews else []
    fields = db.scalars(select(FieldObservation).where(FieldObservation.result_key == task.result_key).order_by(FieldObservation.created_at)).all()
    history = db.scalars(select(TaskEvent).join(Task, Task.id == TaskEvent.task_id).where(Task.result_key == task.result_key)
                         .order_by(TaskEvent.created_at, TaskEvent.id)).all()
    here_d = _here_dict(here) if here else None
    name = (master.name if master else here.name)
    return {
        "task": task_dict(task, names), "outcome": result.outcome, "outcome_label": OUTCOMES[result.outcome],
        "explanation": explanation, "here": here_d,
        "master": {"jsan_id": master.jsan_id, "name": master.name, "latitude": master.latitude, "longitude": master.longitude,
                   "link_reasons": master.link_reasons} if master else None,
        "observations": observations, "nearby_here": nearby[:12],
        "attributes": attribute_grid(here_d, observations), "reference_links": reference_links(focus[0], focus[1], name),
        "reviews": [_review_dict(r, names) for r in reviews], "qc": [_qc_dict(q, names) for q in qcs],
        "field": [{"id": str(f.id), "status": f.status, "data": f.data, "observed_at": _iso(f.observed_at),
                   "verifier": names.get(f.verifier_id)} for f in fields],
        "history": [{"task_id": e.task_id, "event": e.event, "from": e.from_status, "to": e.to_status, "actor": names.get(e.actor_id),
                     "details": e.details, "at": _iso(e.created_at)} for e in history],
        "options": {"evidence_types": {k: v[0] for k, v in EVIDENCE_TYPES.items()}, "delete_reasons": DELETE_REASONS,
                    "attributes": ATTRIBUTES, "field_statuses": FIELD_STATUSES},
        "independent": wf.is_independent(db, task, user),
    }


def _review_dict(r: ReviewDecision, names):
    return {"id": str(r.id), "task_id": r.task_id, "reviewer": names.get(r.reviewer_id), "decision": r.decision,
            "here_place_id": r.here_place_id,
            "attributes": r.attributes, "evidence": r.evidence, "verification_date": _iso(r.verification_date),
            "remarks": r.remarks, "delete_reason": r.delete_reason, "duplicate_of": r.duplicate_of,
            "field_issue": r.field_issue, "confidence_score": r.confidence_score, "rule_check": r.rule_check, "at": _iso(r.created_at)}


def _qc_dict(q: QcDecision, names):
    return {"id": str(q.id), "review_id": str(q.review_id), "qc_user": names.get(q.qc_user_id), "action": q.action,
            "reclassified_to": q.reclassified_to, "remarks": q.remarks, "at": _iso(q.created_at)}


# ---------- Actions ----------
@router.post("/{task_id}/start")
def start(task_id: int, db: Session = Depends(storage), user: User = Depends(current_user)):
    task = _task(db, task_id, user, for_update=True)
    if task.assigned_to == user.id:
        wf.start(db, task, user)
        db.commit()
    return task_dict(task)


class ReviewSubmit(BaseModel):
    decision: Literal["new", "update", "delete", "no_change", "field_review", "hold"]
    attributes: dict = {}
    evidence: list[dict] = Field(default_factory=list, max_length=40)
    verification_date: str | None = None
    remarks: str = Field("", max_length=4000)
    delete_reason: str | None = None
    duplicate_of: str | None = None
    here_place_id: str | None = Field(None, max_length=200)
    field_issue: str | None = Field(None, max_length=2000)


def target_place_id(result: ComparisonResult, chosen: str | None):
    """The HERE record a decision applies to: the reviewer's choice (fallout) or the matched record."""
    return (chosen or "").strip() or result.here_place_id


def _context_for(db, task: Task, result: ComparisonResult, chosen: str | None):
    place_ids = set(db.scalars(select(CustomerPoi.place_id).where(CustomerPoi.dataset_id == task.dataset_id)))
    target = target_place_id(result, chosen)
    return {"has_here": bool(target) and target in place_ids, "place_id": target, "here_place_ids": place_ids,
            "aoi_contains": lambda lon, lat: contains(task.aoi, lon, lat), "category_codes": set(categories())}


@router.post("/{task_id}/review")
def submit_review(task_id: int, body: ReviewSubmit, db: Session = Depends(storage), user: User = Depends(require_roles("reviewer"))):
    task = _task(db, task_id, user, for_update=True)
    _require_mine(task, user, {"review"})
    result = db.get(ComparisonResult, task.result_id)
    payload = body.model_dump()
    if body.here_place_id and body.here_place_id != result.here_place_id and             body.here_place_id not in {c["place_id"] for c in result.explanation.get("candidates", [])}:
        raise HTTPException(422, "Choose the HERE record from this result's candidates.")
    check = validate_decision(payload, _context_for(db, task, result, body.here_place_id))
    if check["errors"]:
        raise HTTPException(422, {"message": "The decision is missing required inputs or evidence.", "issues": check["errors"],
                                  "warnings": check["warnings"]})
    review = ReviewDecision(task_id=task.id, result_id=result.id, result_key=task.result_key, reviewer_id=user.id,
                            decision=body.decision, here_place_id=target_place_id(result, body.here_place_id),
                            attributes=body.attributes, evidence=body.evidence,
                            verification_date=date.fromisoformat(body.verification_date[:10]) if body.verification_date else None,
                            remarks=body.remarks.strip(), delete_reason=body.delete_reason, duplicate_of=body.duplicate_of,
                            field_issue=body.field_issue, confidence_score=check["confidence"]["raw"], rule_check=check)
    db.add(review)
    db.flush()
    if body.decision == "hold":
        wf.log(db, task, user, "held", "on_hold", review=str(review.id), remarks=body.remarks)
    elif body.decision == "field_review":
        wf.complete(db, task, user, "sent_to_field", review=str(review.id))
        wf.spawn(db, task, "field", "field", f"field:{review.id}", user, review_id=review.id, note=body.field_issue or "")
    else:
        wf.complete(db, task, user, "reviewed", decision=body.decision, review=str(review.id))
        queue = "qc_fallout" if result.outcome == "fallout_review" else wf.QC_QUEUES[body.decision]
        wf.spawn(db, task, "qc", queue, f"qc:{review.id}", user, review_id=review.id)
    db.commit()
    return {"review_id": str(review.id), "warnings": check["warnings"], "confidence": check["confidence"]}


@router.post("/{task_id}/resume")
def resume(task_id: int, db: Session = Depends(storage), user: User = Depends(current_user)):
    task = _task(db, task_id, user, for_update=True)
    _require_mine(task, user, {"review", "qc", "field"}, statuses=("on_hold",))
    wf.log(db, task, user, "resumed", "in_progress")
    db.commit()
    return task_dict(task)


class QcSubmit(BaseModel):
    action: Literal["approve", "reject", "return", "reclassify", "field", "hold"]
    reclassified_to: Literal["new", "update", "delete", "no_change"] | None = None
    remarks: str = Field("", max_length=4000)


@router.post("/{task_id}/qc")
def submit_qc(task_id: int, body: QcSubmit, db: Session = Depends(storage), user: User = Depends(require_roles("qc_analyst", "qc_lead"))):
    task = _task(db, task_id, user, for_update=True)
    _require_mine(task, user, {"qc"})
    if not wf.is_independent(db, task, user):
        raise HTTPException(403, "Independent QC: you reviewed or field-verified this record, so someone else must QC it.")
    review = db.get(ReviewDecision, task.review_id)
    if body.action != "approve" and not body.remarks.strip():
        raise HTTPException(422, "Add QC remarks explaining this decision.")
    if body.action == "approve" and review.decision not in ("new", "update", "delete", "no_change"):
        raise HTTPException(422, "This record was sent for field review; reclassify it or return it so the final decision gets reviewed.")
    if body.action == "reclassify" and (not body.reclassified_to or body.reclassified_to == review.decision):
        raise HTTPException(422, "Choose a different classification to reclassify to.")
    if body.action == "approve":
        # QC validates the action itself: re-run the evidence rules on the reviewer's submission.
        result = db.get(ComparisonResult, task.result_id)
        check = validate_decision({"decision": review.decision, "attributes": review.attributes, "evidence": review.evidence,
                                   "verification_date": _iso(review.verification_date), "delete_reason": review.delete_reason,
                                   "duplicate_of": review.duplicate_of, "remarks": review.remarks,
                                   "field_issue": review.field_issue}, _context_for(db, task, result, review.here_place_id))
        if check["errors"]:
            raise HTTPException(422, {"message": "This decision no longer meets the evidence rules; return it for rework.",
                                      "issues": check["errors"]})
    qc = QcDecision(task_id=task.id, review_id=review.id, qc_user_id=user.id, action=body.action,
                    reclassified_to=body.reclassified_to, remarks=body.remarks.strip())
    db.add(qc)
    db.flush()
    original_reviewer = review.reviewer_id
    if body.action == "approve":
        wf.approve(db, task, review, qc)
        wf.complete(db, task, user, "qc_approved", qc=str(qc.id))
    elif body.action == "reject":
        wf.withdraw_approval(db, task)
        wf.complete(db, task, user, "qc_rejected", qc=str(qc.id), remarks=qc.remarks)
    elif body.action in ("return", "reclassify"):
        note = qc.remarks if body.action == "return" else f"Reclassify to {body.reclassified_to.upper()}: {qc.remarks}"
        wf.complete(db, task, user, "qc_returned" if body.action == "return" else "qc_reclassified", qc=str(qc.id))
        wf.spawn(db, task, "review", "rework", f"rework:{qc.id}", user, assigned_to=original_reviewer, note=note, priority=1)
    elif body.action == "field":
        wf.complete(db, task, user, "qc_field_requested", qc=str(qc.id))
        wf.spawn(db, task, "field", "field", f"field:{qc.id}", user, review_id=review.id, note=qc.remarks)
    else:  # hold / escalate to a QC lead
        task.assigned_to, task.queue = None, "escalated"
        wf.log(db, task, user, "escalated", "open", qc=str(qc.id), remarks=qc.remarks)
    db.commit()
    return {"qc_id": str(qc.id), "task": task_dict(task)}


class FieldSubmit(BaseModel):
    status: Literal["existing", "temporarily_closed", "permanently_closed", "moved", "not_found"]
    observed_at: datetime
    gps_latitude: float | None = Field(None, ge=-90, le=90)
    gps_longitude: float | None = Field(None, ge=-180, le=180)
    gps_accuracy_m: float | None = Field(None, ge=0, le=5000)
    display_latitude: float | None = Field(None, ge=-90, le=90)
    display_longitude: float | None = Field(None, ge=-180, le=180)
    routing_latitude: float | None = Field(None, ge=-90, le=90)
    routing_longitude: float | None = Field(None, ge=-180, le=180)
    signage_name: str = Field("", max_length=300)
    category: str = Field("", max_length=200)
    address: str = Field("", max_length=600)
    unit: str = Field("", max_length=100)
    parent: str = Field("", max_length=300)
    phone: str = Field("", max_length=200)
    opening_hours: str = Field("", max_length=600)
    photos: list[str] = Field(default_factory=list, max_length=20)
    remarks: str = Field("", max_length=4000)
    unresolved: list[str] = Field(default_factory=list)


@router.post("/{task_id}/field")
def submit_field(task_id: int, body: FieldSubmit, db: Session = Depends(storage), user: User = Depends(require_roles("field_verifier"))):
    task = _task(db, task_id, user, for_update=True)
    _require_mine(task, user, {"field"})
    if aware(body.observed_at) > now():
        raise HTTPException(422, "The observation time can't be in the future.")
    if body.gps_latitude is None or body.gps_longitude is None or body.gps_accuracy_m is None:
        raise HTTPException(422, "Record the GPS position and its accuracy where the observation was made.")
    if body.status != "not_found" and not body.signage_name.strip() and "name" not in body.unresolved:
        raise HTTPException(422, "Record the visible signage name, or mark the name as unresolved.")
    field = FieldObservation(task_id=task.id, result_key=task.result_key, verifier_id=user.id, status=body.status,
                             data=body.model_dump(mode="json"), observed_at=body.observed_at)
    db.add(field)
    db.flush()
    wf.complete(db, task, user, "field_completed", field=str(field.id), status=body.status)
    # Field results always return to independent QC for final validation.
    wf.spawn(db, task, "qc", "qc_fallout", f"qc-field:{field.id}", user, review_id=task.review_id)
    db.commit()
    return {"field_id": str(field.id)}


class AssignRequest(BaseModel):
    user_id: UUID
    reason: str = Field(..., min_length=3, max_length=500)


@router.post("/{task_id}/assign")
def reassign(task_id: int, body: AssignRequest, db: Session = Depends(storage), user: User = Depends(require_roles(*SUPERVISORS))):
    task = _task(db, task_id, user, for_update=True)
    assignee = db.get(User, body.user_id)
    if not assignee or not assignee.active:
        raise HTTPException(404, "User not found")
    try:
        wf.assign(db, task, assignee, user, body.reason)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    db.commit()
    return task_dict(task, _names(db))


@router.post("/{task_id}/release")
def release(task_id: int, db: Session = Depends(storage), user: User = Depends(current_user)):
    task = _task(db, task_id, user, for_update=True)
    if task.status not in wf.ACTIVE:
        raise HTTPException(409, f"This task is {task.status}.")
    task.assigned_to = None
    task.started_at = None
    wf.log(db, task, user, "released", "open")
    db.commit()
    return task_dict(task)


@router.get("/metrics/overview")
def metrics(db: Session = Depends(storage), user: User = Depends(require_roles(*SUPERVISORS))):
    """Operations dashboard: queue status, productivity, handling time, QC rejection/rework (requirements §10)."""
    by_status = dict(db.execute(select(Task.status, func.count()).group_by(Task.status)).all())
    by_queue = [{"queue": q, "label": wf.QUEUE_LABELS.get(q, q), "status": s, "count": c}
                for q, s, c in db.execute(select(Task.queue, Task.status, func.count()).group_by(Task.queue, Task.status))]
    handling = {}
    for kind in ("review", "qc", "field"):
        rows = db.execute(select(Task.started_at, Task.completed_at).where(
            Task.kind == kind, Task.started_at.is_not(None), Task.completed_at.is_not(None))).all()
        minutes = [(aware(c) - aware(s)).total_seconds() / 60 for s, c in rows if c and s]
        handling[kind] = {"completed": len(minutes), "avg_minutes": round(sum(minutes) / len(minutes), 1) if minutes else None}
    qc = dict(db.execute(select(QcDecision.action, func.count()).group_by(QcDecision.action)).all())
    qc_total = sum(qc.values())
    names = _names(db)
    productivity = [{"user": names.get(uid), "event": ev, "count": c} for uid, ev, c in db.execute(
        select(TaskEvent.actor_id, TaskEvent.event, func.count()).where(TaskEvent.to_status == "completed")
        .group_by(TaskEvent.actor_id, TaskEvent.event))]
    approved = dict(db.execute(select(ApprovedRecord.action, func.count()).group_by(ApprovedRecord.action)).all())
    return {"tasks_by_status": by_status, "queues": by_queue, "handling_time": handling, "qc_actions": qc,
            "qc_rejection_rate": round(qc.get("reject", 0) / qc_total, 3) if qc_total else None,
            "qc_rework_rate": round((qc.get("return", 0) + qc.get("reclassify", 0)) / qc_total, 3) if qc_total else None,
            "field_tasks_open": db.scalar(select(func.count()).select_from(Task).where(Task.kind == "field", Task.status.in_(("open", *wf.ACTIVE)))),
            "approved_for_delivery": approved, "productivity": productivity,
            "note": "Handling time is assignment start to completion (wall time), not active effort; pauses are not yet tracked."}
