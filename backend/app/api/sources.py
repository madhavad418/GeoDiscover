import hashlib
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import audit, current_user, require_roles
from ..models.platform import SourceBatch, SourceObservation, User
from ..services.customer_import import AOIS, MAX_BYTES, ImportInvalid
from ..services.observations import SOURCE_TYPES, parse_observations
from .customer import storage

router = APIRouter(prefix="/sources", tags=["permitted sources"])


def batch_dict(b: SourceBatch):
    return {"id": str(b.id), "aoi": b.aoi, "country": b.country, "source_type": b.source_type,
            "source_type_label": SOURCE_TYPES.get(b.source_type, b.source_type), "source_name": b.source_name,
            "license_reference": b.license_reference, "permitted_use": b.permitted_use,
            "collection_method": b.collection_method, "filename": b.filename, "row_count": b.row_count,
            "created_at": b.created_at.isoformat() if b.created_at else None}


@router.get("/types")
def source_types():
    return {"types": SOURCE_TYPES, "aois": list(AOIS),
            "policy": "Google Places, Grab, Apple and other map providers are reference-only: open them in their own "
                      "viewers during review. Their content is not imported, stored or delivered."}


@router.get("/aois/{aoi}/boundary")
def aoi_boundary(aoi: str, _: User = Depends(current_user)):
    """HERE-supplied AOI boundary (GeoJSON FeatureCollection) for map display."""
    import json
    from ..services.aoi import RESOURCES
    data = json.loads((RESOURCES / "aoi_boundaries.json").read_text(encoding="utf-8"))
    if aoi not in data:
        raise HTTPException(404, "Unknown AOI")
    return {**data[aoi], "name": f"{aoi.replace(' ', '_')}_{AOIS[aoi]}"}


@router.get("/batches")
def list_batches(aoi: str | None = None, db: Session = Depends(storage), _: User = Depends(current_user)):
    query = select(SourceBatch).order_by(SourceBatch.created_at.desc())
    if aoi:
        query = query.where(SourceBatch.aoi == aoi)
    return [batch_dict(b) for b in db.scalars(query)]


@router.post("/batches", status_code=201)
def import_batch(
    aoi: str = Form(...), source_type: str = Form(...), source_name: str = Form(..., max_length=200),
    license_reference: str = Form(..., max_length=2000), permitted_use: str = Form(..., max_length=2000),
    collection_method: str = Form("", max_length=200), file: UploadFile = File(...),
    db: Session = Depends(storage), user: User = Depends(require_roles("ops_manager", "qc_lead")),
):
    if aoi not in AOIS:
        raise HTTPException(422, "Select one of the three assigned AOIs.")
    if source_type not in SOURCE_TYPES:
        raise HTTPException(422, "Choose a permitted source type. Map providers are reference-only and can't be imported.")
    if not license_reference.strip() or not permitted_use.strip():
        raise HTTPException(422, "Record the licence/permission reference and the permitted use for this source.")
    content = file.file.read(MAX_BYTES + 1)
    filename = (file.filename or "upload").replace("\\", "/").split("/")[-1]
    try:
        records, columns, report = parse_observations(content, filename, aoi)
    except ImportInvalid as exc:
        raise HTTPException(422, {"message": str(exc), "issues": exc.issues}) from exc
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(SourceBatch).where(SourceBatch.aoi == aoi, SourceBatch.sha256 == digest))
    if existing:
        raise HTTPException(409, {"message": "This file is already imported for this AOI.", "batch_id": str(existing.id)})
    batch = SourceBatch(aoi=aoi, country=AOIS[aoi], source_type=source_type, source_name=source_name.strip(),
                        license_reference=license_reference.strip(), permitted_use=permitted_use.strip(),
                        collection_method=collection_method.strip() or SOURCE_TYPES[source_type], filename=filename,
                        sha256=digest, row_count=len(records), columns=columns, created_by=user.id)
    db.add(batch)
    db.flush()
    db.add_all(SourceObservation(batch_id=batch.id, retrieved_on=date.today(), **r) for r in records)
    audit(db, user, "import_source_batch", "source_batch", batch.id, aoi=aoi, rows=len(records), **{k: v for k, v in report.items() if k != "mapped_columns"})
    db.commit()
    return {**batch_dict(batch), "report": report}


@router.get("/batches/{batch_id}/observations")
def observations(batch_id: UUID, q: str = Query("", max_length=200), page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=200), db: Session = Depends(storage), _: User = Depends(current_user)):
    batch = db.get(SourceBatch, batch_id)
    if not batch:
        raise HTTPException(404, "Source batch not found")
    conditions = [SourceObservation.batch_id == batch_id]
    if q.strip():
        conditions.append(or_(SourceObservation.name.icontains(q.strip(), autoescape=True),
                              SourceObservation.source_record_id.icontains(q.strip(), autoescape=True)))
    total = db.scalar(select(func.count()).select_from(SourceObservation).where(*conditions))
    rows = db.scalars(select(SourceObservation).where(*conditions).order_by(SourceObservation.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"batch": batch_dict(batch), "total": total, "page": page,
            "records": [observation_dict(o) for o in rows]}


def observation_dict(o: SourceObservation):
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in {
        "id": o.id, "source_record_id": o.source_record_id, "name": o.name, "alt_names": o.alt_names,
        "category_code": o.category_code, "category_name": o.category_name, "address": o.address,
        "street_name": o.street_name, "house_number": o.house_number, "unit": o.unit, "postal_code": o.postal_code,
        "phones": o.phones, "website": o.website, "social_url": o.social_url, "opening_hours": o.opening_hours,
        "latitude": o.latitude, "longitude": o.longitude, "routing_latitude": o.routing_latitude,
        "routing_longitude": o.routing_longitude, "business_status": o.business_status, "observed_on": o.observed_on,
        "retrieved_on": o.retrieved_on, "source_url": o.source_url, "here_place_id": o.here_place_id,
    }.items()}
