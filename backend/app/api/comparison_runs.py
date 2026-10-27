import csv
import io
from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session

from ..auth import audit, can_access_aoi, current_user, require_roles
from ..models.customer import CustomerPoi
from ..models.platform import ComparisonResult, ComparisonRun, MasterPoi, SourceBatch, SourceObservation, Task, User
from ..services.matching import OUTCOMES, RULES_VERSION, compare, sha
from ..services.reference import chain_names
from ..services.workflow import SOURCE_BACKED, generate_review_tasks
from .customer import get_dataset, storage

router = APIRouter(prefix="/comparison", tags=["HERE comparison"])
SUPERVISORS = ("ops_manager", "qc_lead")


class RunRequest(BaseModel):
    dataset_id: UUID
    batch_ids: list[UUID] | None = None
    force: bool = False


class TaskRequest(BaseModel):
    include: list[str] = list(SOURCE_BACKED)


def run_dict(run: ComparisonRun, reused=False):
    return {"id": str(run.id), "dataset_id": str(run.dataset_id), "aoi": run.aoi, "rules_version": run.rules_version,
            "batch_ids": run.batch_ids, "stats": run.stats, "reused": reused,
            "created_at": run.created_at.isoformat() if run.created_at else None, "outcome_labels": OUTCOMES}


def _get_run(db, run_id, user):
    run = db.get(ComparisonRun, run_id)
    if not run:
        raise HTTPException(404, "Comparison run not found")
    if not can_access_aoi(user, run.aoi):
        raise HTTPException(403, "This run is outside your assigned areas.")
    return run


@router.post("/runs", status_code=201)
def create_run(body: RunRequest, db: Session = Depends(storage), user: User = Depends(require_roles(*SUPERVISORS))):
    dataset = get_dataset(db, body.dataset_id)
    query = select(SourceBatch).where(SourceBatch.aoi == dataset.aoi)
    if body.batch_ids:
        query = query.where(SourceBatch.id.in_(body.batch_ids))
    batches = db.scalars(query).all()
    if body.batch_ids and len(batches) != len(set(body.batch_ids)):
        raise HTTPException(422, "Every selected source batch must belong to this baseline's AOI.")
    if not batches:
        raise HTTPException(422, "Import at least one permitted source batch for this AOI before comparing.")
    fingerprint = sha(dataset.sha256, *sorted(b.sha256 for b in batches), RULES_VERSION)
    if not body.force:
        previous = db.scalar(select(ComparisonRun).where(ComparisonRun.dataset_id == dataset.id,
                                                         ComparisonRun.fingerprint == fingerprint)
                             .order_by(ComparisonRun.created_at.desc()))
        if previous:
            return run_dict(previous, reused=True)

    here_rows = [dict(r._mapping) for r in db.execute(select(
        CustomerPoi.id, CustomerPoi.place_id, CustomerPoi.name, CustomerPoi.category_code, CustomerPoi.category_name,
        CustomerPoi.latitude, CustomerPoi.longitude, CustomerPoi.address, CustomerPoi.raw).where(CustomerPoi.dataset_id == dataset.id))]
    meta = {b.id: b for b in batches}
    observations = []
    for o in db.scalars(select(SourceObservation).where(SourceObservation.batch_id.in_(meta))):
        b = meta[o.batch_id]
        observations.append({c: getattr(o, c) for c in (
            "id", "batch_id", "source_record_id", "name", "alt_names", "category_code", "category_name", "latitude", "longitude",
            "phones", "website", "social_url", "house_number", "street_name", "unit", "postal_code", "business_status",
            "opening_hours", "address", "here_place_id", "observed_on", "source_url")} |
            {"source_type": b.source_type, "source_name": b.source_name, "observed_on": o.observed_on.isoformat() if o.observed_on else None})
    output = compare(here_rows, observations, dataset.country, str(dataset.id), chain_names(dataset.country))
    stats = output["stats"] | {
        "here_by_category": Counter(r["category_name"] or r["category_code"] or "Uncategorized" for r in here_rows).most_common(),
        "sources": [{"id": str(b.id), "name": b.source_name, "type": b.source_type, "rows": b.row_count} for b in batches],
    }
    run = ComparisonRun(dataset_id=dataset.id, aoi=dataset.aoi, rules_version=RULES_VERSION, fingerprint=fingerprint,
                        batch_ids=[str(b.id) for b in batches], stats=stats, created_by=user.id)
    db.add(run)
    db.flush()
    master_ids = {}
    for m in output["masters"]:
        row = MasterPoi(run_id=run.id, master_key=m["master_key"], jsan_id=m["jsan_id"], name=m["name"],
                        category_code=m["category_code"], latitude=m["lat"], longitude=m["lon"],
                        observation_ids=m["observation_ids"], link_reasons=m["link_reasons"])
        db.add(row)
        db.flush()
        master_ids[m["master_key"]] = row.id
    rows = [{"run_id": run.id, "result_key": r["result_key"], "content_hash": r["content_hash"], "outcome": r["outcome"],
             "master_id": master_ids.get(r["master_key"]), "here_poi_id": r["here_id"], "here_place_id": r["here_place_id"],
             "distance_m": r["distance_m"], "band": r["band"], "decision_rule": r["decision_rule"], "priority": r["priority"],
             "explanation": r["explanation"]} for r in output["results"]]
    for start in range(0, len(rows), 2000):
        db.execute(insert(ComparisonResult), rows[start:start + 2000])
    audit(db, user, "comparison_run", "comparison_run", run.id, dataset=str(dataset.id), outcomes=stats["outcomes"])
    db.commit()
    return run_dict(run)


@router.get("/runs")
def list_runs(dataset_id: UUID, db: Session = Depends(storage), user: User = Depends(current_user)):
    runs = db.scalars(select(ComparisonRun).where(ComparisonRun.dataset_id == dataset_id)
                      .order_by(ComparisonRun.created_at.desc()).limit(20)).all()
    return [run_dict(r) for r in runs if can_access_aoi(user, r.aoi)]


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, db: Session = Depends(storage), user: User = Depends(current_user)):
    run = _get_run(db, run_id, user)
    tasks = dict(db.execute(select(Task.status, func.count()).where(Task.run_id == run.id).group_by(Task.status)).all())
    return {**run_dict(run), "tasks": tasks}


def _summary(r: ComparisonResult):
    e = r.explanation
    here, master = e.get("here") or {}, e.get("master") or {}
    return {"id": r.id, "outcome": r.outcome, "label": OUTCOMES[r.outcome], "priority": r.priority,
            "here_place_id": r.here_place_id, "here_name": here.get("name"), "jsan_id": master.get("jsan_id"),
            "master_name": master.get("name"), "sources": master.get("sources", []), "distance_m": r.distance_m,
            "band": r.band, "decision_rule": r.decision_rule, "reasons": e.get("reasons", []),
            "changed_fields": [d["field"] for d in e.get("changed_fields", [])],
            "candidate_count": len(e.get("candidates", [])),
            "lat": (master or here).get("lat"), "lon": (master or here).get("lon")}


@router.get("/runs/{run_id}/results")
def results(run_id: UUID, outcome: str | None = None, q: str = Query("", max_length=200), page: int = Query(1, ge=1),
            page_size: int = Query(50, ge=1, le=500), db: Session = Depends(storage), user: User = Depends(current_user)):
    _get_run(db, run_id, user)
    conditions = [ComparisonResult.run_id == run_id]
    if outcome:
        conditions.append(ComparisonResult.outcome == outcome)
    if q.strip():
        conditions.append(or_(ComparisonResult.here_place_id.icontains(q.strip(), autoescape=True),
                              ComparisonResult.master_id.in_(select(MasterPoi.id).where(
                                  MasterPoi.run_id == run_id, MasterPoi.name.icontains(q.strip(), autoescape=True)))))
    total = db.scalar(select(func.count()).select_from(ComparisonResult).where(*conditions))
    rows = db.scalars(select(ComparisonResult).where(*conditions).order_by(ComparisonResult.priority, ComparisonResult.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "results": [_summary(r) for r in rows]}


@router.get("/results/{result_id}")
def result_detail(result_id: int, db: Session = Depends(storage), user: User = Depends(current_user)):
    r = db.get(ComparisonResult, result_id)
    if not r:
        raise HTTPException(404, "Result not found")
    _get_run(db, r.run_id, user)
    return {**_summary(r), "explanation": r.explanation}


@router.get("/runs/{run_id}/map")
def result_map(run_id: UUID, db: Session = Depends(storage), user: User = Depends(current_user)):
    """Points for the map: discovered location for source-backed results, HERE location otherwise."""
    _get_run(db, run_id, user)
    features = []
    for r in db.scalars(select(ComparisonResult).where(ComparisonResult.run_id == run_id)):
        s = _summary(r)
        if s["lat"] is None:
            continue
        here = r.explanation.get("here") or {}
        features.append({"type": "Feature", "id": r.id, "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                         "properties": {"result_id": r.id, "outcome": r.outcome, "label": s["label"],
                                        "name": s["master_name"] or s["here_name"], "here_place_id": r.here_place_id or "",
                                        "jsan_id": s["jsan_id"] or "", "here_lat": here.get("lat"), "here_lon": here.get("lon"),
                                        "distance_m": r.distance_m}})
    return {"type": "FeatureCollection", "features": features}


def _csv(value):
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/runs/{run_id}/report.csv")
def report(run_id: UUID, db: Session = Depends(storage), user: User = Depends(require_roles(*SUPERVISORS, "qc_analyst"))):
    """Internal comparison report (not a customer deliverable)."""
    run = _get_run(db, run_id, user)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["outcome", "here_place_id", "here_name", "jsan_id", "discovered_name", "sources", "distance_m", "band",
                     "rule", "changed_fields", "candidates", "reasons"])
    for r in db.scalars(select(ComparisonResult).where(ComparisonResult.run_id == run.id).order_by(ComparisonResult.priority)):
        s = _summary(r)
        writer.writerow([_csv(v) for v in (s["label"], s["here_place_id"], s["here_name"], s["jsan_id"], s["master_name"],
                                            "; ".join(s["sources"]), s["distance_m"], s["band"], s["decision_rule"],
                                            ", ".join(s["changed_fields"]), s["candidate_count"], " ".join(s["reasons"]))])
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="comparison-{run.aoi.replace(" ", "-").lower()}-{str(run.id)[:8]}.csv"'})


@router.post("/runs/{run_id}/tasks")
def create_tasks(run_id: UUID, body: TaskRequest, db: Session = Depends(storage), user: User = Depends(require_roles(*SUPERVISORS))):
    run = _get_run(db, run_id, user)
    unknown = set(body.include) - set(OUTCOMES)
    if unknown:
        raise HTTPException(422, f"Unknown outcome: {', '.join(sorted(unknown))}")
    counts = generate_review_tasks(db, run, tuple(body.include), actor=user)
    audit(db, user, "generate_tasks", "comparison_run", run.id, **counts)
    db.commit()
    return counts
