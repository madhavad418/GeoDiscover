import hashlib
import json
import threading
from collections import OrderedDict
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..db import get_db
from ..models.platform import User
from ..models.customer import CustomerDataset, CustomerPoi
from ..services.customer_import import AOIS, MAX_BYTES, ImportInvalid, parse_file

router = APIRouter(prefix="/customer-data", tags=["customer data"])


def storage(db: Session = Depends(get_db)):
    try:
        yield db
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, "Customer storage is unavailable. Check the database connection and run the PostGIS migrations.") from exc


def dataset_dict(item):
    return {k: getattr(item, k) for k in ("id", "filename", "customer", "aoi", "country", "row_count", "columns", "created_at")}


def get_dataset(db, dataset_id):
    item = db.get(CustomerDataset, dataset_id)
    if item is None:
        raise HTTPException(404, "Dataset not found")
    return item


@router.get("/datasets")
def datasets(db: Session = Depends(storage)):
    items = db.scalars(select(CustomerDataset).order_by(CustomerDataset.created_at.desc())).all()
    return {"datasets": [dataset_dict(d) for d in items], "aois": AOIS}


@router.post("/imports", status_code=201)
def import_data(aoi: str = Form(...), file: UploadFile = File(...), db: Session = Depends(storage),
                _: User = Depends(require_roles("ops_manager", "qc_lead"))):
    content = file.file.read(MAX_BYTES + 1)
    try:
        records, columns = parse_file(content, file.filename or "", aoi)
    except ImportInvalid as exc:
        raise HTTPException(422, {"message": str(exc), "issues": exc.issues}) from exc
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(CustomerDataset).where(CustomerDataset.aoi == aoi, CustomerDataset.sha256 == digest))
    if existing:
        raise HTTPException(409, {"message": "This file is already saved for this AOI.", "dataset_id": str(existing.id)})
    dataset = CustomerDataset(filename=(file.filename or "upload").replace("\\", "/").split("/")[-1],
                              customer="HERE", aoi=aoi, country=AOIS[aoi], sha256=digest,
                              row_count=len(records), columns=columns)
    statement = text("""
        INSERT INTO customer_pois
        (dataset_id, place_id, name, category_code, category_name, country, address,
         latitude, longitude, routing_latitude, routing_longitude, raw, display_point, routing_point)
        VALUES (:dataset_id, :place_id, :name, :category_code, :category_name, :country, :address,
                :latitude, :longitude, :routing_latitude, :routing_longitude, CAST(:raw AS jsonb),
                ST_SetSRID(ST_MakePoint(:longitude, :latitude),4326),
                CASE WHEN CAST(:routing_latitude AS double precision) IS NULL THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint(:routing_longitude, :routing_latitude),4326) END)
    """)
    try:
        db.add(dataset)
        db.flush()
        for start in range(0, len(records), 1000):
            db.execute(statement, [{**r, "dataset_id": dataset.id, "raw": json.dumps(r["raw"], ensure_ascii=False)}
                                   for r in records[start:start + 1000]])
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This import conflicts with an existing dataset. Refresh and try again.") from exc
    return dataset_dict(dataset)


@router.get("/datasets/{dataset_id}/records")
def records(dataset_id: UUID, q: str = Query("", max_length=200), category: str = Query("", max_length=300),
            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(storage)):
    dataset = get_dataset(db, dataset_id)
    conditions = [CustomerPoi.dataset_id == dataset_id]
    if q.strip():
        # Literal substring search; SQL wildcards in user input remain literal.
        conditions.append(or_(*(c.icontains(q.strip(), autoescape=True)
                               for c in (CustomerPoi.name, CustomerPoi.place_id, CustomerPoi.address))))
    if category:
        conditions.append(CustomerPoi.category_name == category)
    total = db.scalar(select(func.count()).select_from(CustomerPoi).where(*conditions))
    items = db.scalars(select(CustomerPoi).where(*conditions).order_by(CustomerPoi.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    categories = db.scalars(select(CustomerPoi.category_name).where(CustomerPoi.dataset_id == dataset_id,
                           CustomerPoi.category_name.is_not(None)).distinct().order_by(CustomerPoi.category_name)).all()
    fields = ("id", "place_id", "name", "category_code", "category_name", "country", "address", "latitude",
              "longitude", "routing_latitude", "routing_longitude", "raw")
    return {"dataset": dataset_dict(dataset), "records": [{k: getattr(r, k) for k in fields} for r in items],
            "total": total, "page": page, "page_size": page_size, "categories": categories}


# Saved datasets are immutable (a changed file becomes a new dataset), so the serialized GeoJSON
# can be cached per dataset. A per-dataset lock makes concurrent first views build it only once.
_GEOJSON_CACHE_SIZE = 4
_geojson_cache: OrderedDict[UUID, bytes] = OrderedDict()
_geojson_locks: dict[UUID, threading.Lock] = {}
_cache_lock = threading.Lock()


def _build_geojson(db: Session, dataset: CustomerDataset) -> bytes:
    items = db.execute(select(CustomerPoi.raw, CustomerPoi.place_id, CustomerPoi.name, CustomerPoi.category_name,
                              CustomerPoi.longitude, CustomerPoi.latitude).where(CustomerPoi.dataset_id == dataset.id)
                       .order_by(CustomerPoi.id)).all()
    collection = {"type": "FeatureCollection", "name": f"{dataset.aoi.replace(' ', '_')}_{dataset.country}", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.longitude, r.latitude]},
         "properties": {**r.raw, "placeid": r.place_id, "name1": r.name, "primarycategorynm": r.category_name}}
        for r in items]}
    return json.dumps(collection, ensure_ascii=False, separators=(",", ":")).encode()


@router.get("/datasets/{dataset_id}/geojson")
def geojson(dataset_id: UUID, db: Session = Depends(storage)):
    dataset = get_dataset(db, dataset_id)
    with _cache_lock:
        lock = _geojson_locks.setdefault(dataset_id, threading.Lock())
    with lock:
        with _cache_lock:
            body = _geojson_cache.get(dataset_id)
            if body is not None:
                _geojson_cache.move_to_end(dataset_id)
        if body is None:
            body = _build_geojson(db, dataset)
            with _cache_lock:
                _geojson_cache[dataset_id] = body
                while len(_geojson_cache) > _GEOJSON_CACHE_SIZE:
                    _geojson_cache.popitem(last=False)
    return Response(body, media_type="application/geo+json",
                    headers={"Cache-Control": "private, max-age=86400", "ETag": f'"{dataset_id}"'})
