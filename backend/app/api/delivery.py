import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import audit, can_access_aoi, current_user, require_roles
from ..config import get_settings
from ..models.customer import CustomerPoi
from ..models.platform import (
    ApprovedRecord, ComparisonResult, DeliveryFile, DeliverySnapshot, FieldObservation, MasterPoi, QcDecision,
    ReviewDecision, SourceBatch, SourceObservation, User,
)
from ..services import delivery as dl
from .customer import get_dataset, storage

router = APIRouter(prefix="/delivery", tags=["customer delivery"])
EXPORTERS = ("ops_manager", "qc_lead")


def assemble(db: Session, dataset):
    """Approved decisions joined with their review, QC, comparison result and HERE baseline row."""
    approved = db.scalars(select(ApprovedRecord).where(ApprovedRecord.dataset_id == dataset.id,
                                                        ApprovedRecord.action.in_(dl.ACTIONS))).all()
    here_rows = {p.place_id: p for p in db.scalars(select(CustomerPoi).where(CustomerPoi.dataset_id == dataset.id))}
    records = []
    for a in approved:
        review = db.get(ReviewDecision, a.review_id)
        qc = db.get(QcDecision, a.qc_id)
        result = db.get(ComparisonResult, review.result_id)
        master = db.get(MasterPoi, result.master_id) if result.master_id else None
        here = here_rows.get(review.here_place_id) if review.here_place_id else None
        qc_fielded = db.scalar(select(func.count()).select_from(FieldObservation).where(
            FieldObservation.result_key == a.result_key, FieldObservation.verifier_id == qc.qc_user_id))
        licensed = True
        if master:
            licensed = all(b.license_reference.strip() for b in db.scalars(
                select(SourceBatch).join(SourceObservation, SourceObservation.batch_id == SourceBatch.id)
                .where(SourceObservation.id.in_(master.observation_ids))))
        records.append({
            "action": a.action, "result_key": a.result_key, "jsan_id": master.jsan_id if master else None,
            "here_place_id": review.here_place_id, "here_raw": here.raw if here else {},
            "here": {"latitude": here.latitude, "longitude": here.longitude, "routing_latitude": here.routing_latitude,
                     "routing_longitude": here.routing_longitude} if here else {},
            "review": {"attributes": review.attributes, "evidence": review.evidence, "remarks": review.remarks,
                       "verification_date": review.verification_date.isoformat() if review.verification_date else None,
                       "delete_reason": review.delete_reason, "duplicate_of": review.duplicate_of, "rule_check": review.rule_check},
            "qc_independent": qc.action == "approve" and qc.qc_user_id != review.reviewer_id and not qc_fielded,
            "sources_licensed": licensed,
        })
    return records, set(here_rows), len(approved)


def preflight(db, dataset):
    template_issues = dl.check_templates()
    records, here_ids, approved_total = assemble(db, dataset)
    conflicts = dl.cross_file_conflicts(records)
    eligible, held_back, majors, seen = [], [], [], set()
    for r in records:
        blockers, record_majors = dl.record_checks(r, dataset.aoi, dataset.country, here_ids, seen)
        if r.get("here_place_id") in conflicts:
            blockers.append("Cross-file conflict: the same HERE record appears in more than one action")
        label = r["jsan_id"] if r["action"] == "new" else r.get("here_place_id")
        if blockers:
            held_back.append({"record": label, "action": r["action"], "reason": "; ".join(blockers)})
        else:
            eligible.append(r)
            majors += [{"record": label, "action": r["action"], "issue": m} for m in record_majors]
    counts = {a: sum(1 for r in eligible if r["action"] == a) for a in dl.ACTIONS}
    return {"template_issues": template_issues, "eligible": eligible, "held_back": held_back, "majors": majors,
            "counts": counts, "approved_total": approved_total, "here_total": len(here_ids),
            "can_build": not template_issues and bool(eligible)}


@router.get("/datasets/{dataset_id}/preflight")
def preflight_report(dataset_id: UUID, db: Session = Depends(storage), user: User = Depends(require_roles(*EXPORTERS, "qc_analyst"))):
    dataset = get_dataset(db, dataset_id)
    if not can_access_aoi(user, dataset.aoi):
        raise HTTPException(403, "This dataset is outside your assigned areas.")
    report = preflight(db, dataset)
    return {k: v for k, v in report.items() if k != "eligible"} | {"assumptions": dl.ASSUMPTIONS}


@router.post("/datasets/{dataset_id}/snapshots", status_code=201)
def build_snapshot(dataset_id: UUID, db: Session = Depends(storage), user: User = Depends(require_roles(*EXPORTERS))):
    dataset = get_dataset(db, dataset_id)
    report = preflight(db, dataset)
    if report["template_issues"]:
        raise HTTPException(422, {"message": "Template check failed; nothing was generated.", "issues": report["template_issues"]})
    if not report["eligible"]:
        raise HTTPException(422, "No QC-approved records pass the delivery gates yet.")
    previous = db.scalar(select(func.count()).select_from(DeliverySnapshot).where(DeliverySnapshot.dataset_id == dataset.id))
    version = f"1.{previous}"
    settings = get_settings()
    files, counts = dl.build_package(supplier=settings.supplier_name, contact=settings.supplier_contact, aoi=dataset.aoi,
                                     country=dataset.country, version=version, records=report["eligible"],
                                     held_back=report["held_back"], majors=report["majors"], here_total=report["here_total"],
                                     approved_total=report["approved_total"])
    checks = [{"id": "templates", "status": "pass"}] + \
             [{"id": "held_back", "status": "withheld" if report["held_back"] else "pass", "count": len(report["held_back"])},
              {"id": "majors", "status": "disclosed" if report["majors"] else "pass", "count": len(report["majors"])}]
    snapshot = DeliverySnapshot(dataset_id=dataset.id, aoi=dataset.aoi, version=version, created_by=user.id,
                                checks=checks + [{"held_back": report["held_back"], "majors": report["majors"]}], counts=counts)
    db.add(snapshot)
    db.flush()
    for kind, (name, content, rows, customer) in files.items():
        db.add(DeliveryFile(snapshot_id=snapshot.id, kind=kind, filename=name, sha256=hashlib.sha256(content).hexdigest(),
                            row_count=rows, customer_facing=customer, content=content))
    audit(db, user, "build_delivery", "delivery_snapshot", snapshot.id, version=version, counts=counts,
          held_back=len(report["held_back"]), majors=len(report["majors"]))
    db.commit()
    return snapshot_dict(db, snapshot)


def snapshot_dict(db, s: DeliverySnapshot):
    files = db.execute(select(DeliveryFile.id, DeliveryFile.kind, DeliveryFile.filename, DeliveryFile.sha256,
                              DeliveryFile.row_count, DeliveryFile.customer_facing).where(DeliveryFile.snapshot_id == s.id)).all()
    return {"id": str(s.id), "aoi": s.aoi, "version": s.version, "counts": s.counts, "created_at": s.created_at.isoformat() if s.created_at else None,
            "files": [dict(f._mapping) for f in files]}


@router.get("/datasets/{dataset_id}/snapshots")
def list_snapshots(dataset_id: UUID, db: Session = Depends(storage), _: User = Depends(current_user)):
    rows = db.scalars(select(DeliverySnapshot).where(DeliverySnapshot.dataset_id == dataset_id).order_by(DeliverySnapshot.created_at.desc()))
    return [snapshot_dict(db, s) for s in rows]


@router.get("/files/{file_id}")
def download(file_id: int, db: Session = Depends(storage), _: User = Depends(require_roles(*EXPORTERS, "qc_analyst"))):
    f = db.get(DeliveryFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    media = "application/zip" if f.filename.endswith(".zip") else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(f.content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{f.filename}"'})
