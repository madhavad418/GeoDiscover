import csv
import io
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.comparison import PoiComparisonReview
from ..models.customer import CustomerDataset, CustomerPoi
from ..services.comparison import PROVIDERS, build_demo_proposals
from .customer import dataset_dict, get_dataset, storage

router = APIRouter(prefix="/customer-data", tags=["POI comparison"])
PROVIDER_IDS = {provider["id"] for provider in PROVIDERS}
DEMO_BASELINE_SIZE = 10


class ReviewUpdate(BaseModel):
    status: Literal["pending", "approved", "rejected"]
    note: str = Field(default="", max_length=1000)


def _demo_proposals(db: Session, dataset: CustomerDataset):
    records = db.scalars(
        select(CustomerPoi.raw)
        .where(CustomerPoi.dataset_id == dataset.id)
        .order_by(CustomerPoi.id)
        .limit(DEMO_BASELINE_SIZE)
    ).all()
    return build_demo_proposals(records, dataset.aoi)


def _review_values(reviews):
    return {
        (review.provider, review.record_key): {
            "review_status": review.status,
            "review_note": review.note,
            "reviewed_at": review.updated_at.isoformat() if review.updated_at else None,
        }
        for review in reviews
    }


def _with_reviews(proposals, review_values):
    return {
        provider_id: [
            {**proposal, **review_values.get((provider_id, proposal["key"]), {})}
            for proposal in provider_proposals
        ]
        for provider_id, provider_proposals in proposals.items()
    }


@router.get("/datasets/{dataset_id}/comparison")
def comparison(dataset_id: UUID, db: Session = Depends(storage)):
    dataset = get_dataset(db, dataset_id)
    proposals = _demo_proposals(db, dataset)
    reviews = db.scalars(
        select(PoiComparisonReview).where(PoiComparisonReview.dataset_id == dataset_id)
    ).all()
    return {
        "dataset": dataset_dict(dataset),
        "demo_only": True,
        "providers": [
            {
                **provider,
                "proposals": _with_reviews(proposals, _review_values(reviews))[provider["id"]],
            }
            for provider in PROVIDERS
        ],
        "rules": {
            "matching": "Exact place ID first; otherwise normalized name, compatible category and within 100 m.",
            "delete": "Only an explicit delete proposal matched to a HERE place can be classified as Delete.",
            "review": "Only approved decisions are included in the delivery CSV.",
        },
    }


@router.put("/datasets/{dataset_id}/comparison/{provider}/{record_key}")
def update_review(
    dataset_id: UUID,
    provider: str,
    record_key: str,
    review: ReviewUpdate,
    db: Session = Depends(storage),
):
    if provider not in PROVIDER_IDS:
        raise HTTPException(404, "Comparison provider not found")
    dataset = get_dataset(db, dataset_id)
    proposals = _demo_proposals(db, dataset).get(provider, [])
    if not any(proposal["key"] == record_key for proposal in proposals):
        raise HTTPException(404, "Comparison proposal not found")

    def existing():
        return db.scalar(
            select(PoiComparisonReview).where(
                PoiComparisonReview.dataset_id == dataset_id,
                PoiComparisonReview.provider == provider,
                PoiComparisonReview.record_key == record_key,
            )
        )

    saved = existing()
    if saved is None:
        saved = PoiComparisonReview(
            dataset_id=dataset_id,
            provider=provider,
            record_key=record_key,
            status=review.status,
            note=review.note.strip(),
        )
        db.add(saved)
    else:
        saved.status = review.status
        saved.note = review.note.strip()
    try:
        db.commit()
    except IntegrityError:
        # Another reviewer saved the same proposal first; apply this decision on top of theirs.
        db.rollback()
        saved = existing()
        saved.status = review.status
        saved.note = review.note.strip()
        db.commit()
    db.refresh(saved)
    return {
        "provider": saved.provider,
        "record_key": saved.record_key,
        "status": saved.status,
        "note": saved.note,
        "updated_at": saved.updated_at.isoformat() if saved.updated_at else None,
    }


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    return f"'{text}" if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


@router.get("/datasets/{dataset_id}/comparison/delivery.csv")
def comparison_delivery(dataset_id: UUID, db: Session = Depends(storage)):
    dataset = get_dataset(db, dataset_id)
    proposals = _demo_proposals(db, dataset)
    reviews = db.scalars(
        select(PoiComparisonReview).where(
            PoiComparisonReview.dataset_id == dataset_id,
            PoiComparisonReview.status == "approved",
        )
    ).all()
    review_values = _review_values(reviews)
    fields = (
        "action", "provider", "record_key", "matched_place_id", "match_method",
        "match_confidence", "changed_fields", "base_name", "proposed_name",
        "base_category", "proposed_category", "base_address", "proposed_address",
        "base_latitude", "base_longitude", "proposed_latitude", "proposed_longitude",
        "review_note", "reviewed_at",
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for provider in PROVIDERS:
        for proposal in proposals[provider["id"]]:
            review = review_values.get((provider["id"], proposal["key"]))
            if not review:
                continue
            base = proposal["base"] or {}
            proposed = proposal["proposed"] or {}
            row = {
                "action": proposal["action"].upper(),
                "provider": provider["name"],
                "record_key": proposal["key"],
                "matched_place_id": base.get("place_id", ""),
                "match_method": proposal["match_method"] or "",
                "match_confidence": proposal["match_confidence"],
                "changed_fields": ", ".join(proposal["changed_fields"]),
                "base_name": base.get("name", ""),
                "proposed_name": proposed.get("name", ""),
                "base_category": base.get("category_name") or base.get("category_code") or "",
                "proposed_category": proposed.get("category_name") or proposed.get("category_code") or "",
                "base_address": base.get("address", ""),
                "proposed_address": proposed.get("address", ""),
                "base_latitude": base.get("latitude", ""),
                "base_longitude": base.get("longitude", ""),
                "proposed_latitude": proposed.get("latitude", ""),
                "proposed_longitude": proposed.get("longitude", ""),
                "review_note": review["review_note"],
                "reviewed_at": review["reviewed_at"],
            }
            writer.writerow({key: _csv_value(value) for key, value in row.items()})
    filename = f"{dataset.aoi.lower().replace(' ', '-')}-poi-decisions.csv"
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
