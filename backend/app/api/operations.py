import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .customer import get_dataset, storage
from ..models.operations import PocPreflightRun
from ..services.poc_rules import STAGES, CLARIFICATIONS
from ..services.providers import diagnose, provider_status, ProviderError

router = APIRouter(prefix='/poc', tags=['POC operations'])
RESOURCES = Path(__file__).resolve().parents[1] / 'resources'
ASSESSMENT = RESOURCES / 'POC_FINAL_REQUIREMENTS_ASSESSMENT.md'
_probe_times = {}
_probe_lock = threading.Lock()


@lru_cache
def package_audit():
    return json.loads((RESOURCES / 'poc_audit.json').read_text(encoding='utf-8'))


def aoi_for(name):
    aoi = next((a for a in package_audit()['aois'] if a['name'] == name), None)
    if not aoi:
        raise HTTPException(422, 'Select one of the supplied AOIs.')
    return aoi


@router.get('/assessment')
def assessment(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return {'audit': package_audit(), 'providers': provider_status(), 'stages': STAGES,
            'clarifications': CLARIFICATIONS, 'submission_date': '2026-11-13',
            'scope': 'Package audit, live baseline preflight and provider connection diagnostics. Full operational delivery is not yet implemented.'}


@router.get('/assessment.md')
def assessment_download():
    return FileResponse(ASSESSMENT, media_type='text/markdown', filename='JSAN_POC_Assessment_20261027.md')


class ProbeRequest(BaseModel):
    aoi: Literal['Divisoria', 'Kampung Bali', 'Thanon Phaya Thai']


def local_operator(request: Request):
    # Paid calls stay local until the role-based login module is implemented.
    if not request.client or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(403, 'Provider diagnostics are available only in the local operator workspace until role-based login is configured.')


@router.post('/providers/{provider}/diagnose', dependencies=[Depends(local_operator)])
def diagnose_provider(provider: Literal['google', 'grab', 'apple'], request: ProbeRequest, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    with _probe_lock:
        if time.monotonic() - _probe_times.get(provider, float('-inf')) < 30:
            raise HTTPException(429, 'Please wait 30 seconds between tests for this provider.')
        _probe_times[provider] = time.monotonic()
    try:
        return {**diagnose(provider, aoi_for(request.aoi)), 'checked_at': datetime.now(timezone.utc).isoformat()}
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from None


@router.post('/datasets/{dataset_id}/preflight')
def preflight(dataset_id: UUID, db: Session = Depends(storage)):
    dataset = get_dataset(db, dataset_id)
    aoi = aoi_for(dataset.aoi)
    boundaries = json.loads((RESOURCES / 'aoi_boundaries.json').read_text(encoding='utf-8'))
    boundary = {'type':'GeometryCollection', 'geometries':[f['geometry'] for f in boundaries[dataset.aoi]['features']]}
    params = {'id': dataset_id, 'boundary': json.dumps(boundary), 'codes': package_audit()['category_codes'], 'country': aoi['country']}
    counts = dict(db.execute(text("""
      WITH boundary AS (SELECT ST_UnaryUnion(ST_SetSRID(ST_GeomFromGeoJSON(:boundary),4326)) AS geom)
      SELECT count(*) AS total,
        count(*) - count(DISTINCT place_id) AS duplicate_ids,
        count(*) FILTER (WHERE trim(place_id)='' OR trim(name)='') AS missing_identity,
        count(*) FILTER (WHERE country<>:country) AS wrong_country,
        count(*) FILTER (WHERE latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180) AS invalid_coordinates,
        count(*) FILTER (WHERE NOT ST_Covers(boundary.geom,display_point)) AS outside_boundary,
        count(*) FILTER (WHERE category_code IS NULL OR NOT (category_code = ANY(:codes))) AS unmapped_categories,
        count(*) FILTER (WHERE COALESCE(NULLIF(raw->>'last_verified_date',''),NULLIF(raw->>'last_verified',''),NULLIF(raw->>'verification_date',''),'')='') AS missing_verification_dates
      FROM customer_pois CROSS JOIN boundary WHERE dataset_id=:id
    """), params).mappings().one())
    checks = []
    for key, label, severity in [
        ('duplicate_ids','Unique place IDs','blocker'), ('missing_identity','Required ID and name','blocker'),
        ('wrong_country','Country matches AOI','major'), ('invalid_coordinates','WGS84 coordinate ranges','major'),
        ('outside_boundary','Display point inside exact AOI','major'), ('unmapped_categories','Category reference coverage','needs_alignment'),
        ('missing_verification_dates','Last verification date supplied','needs_enrichment')]:
        checks.append({'id': key, 'name': label, 'affected': counts[key], 'status': 'pass' if counts[key] == 0 else severity})
    checks.append({'id':'row_count','name':'Imported count reconciles',
                   'affected':abs(counts['total']-dataset.row_count), 'status':'pass' if counts['total']==dataset.row_count else 'blocker'})
    report = {'dataset_id':str(dataset.id), 'aoi':dataset.aoi, 'filename':dataset.filename, 'rows':counts['total'],
              'checked_at':datetime.now(timezone.utc).isoformat(), 'rules_version':'poc-preflight-20261027-v1',
              'input_sha256':dataset.sha256, 'boundary_sha256':hashlib.sha256(json.dumps(boundary,sort_keys=True).encode()).hexdigest(),
              'checks':checks, 'delivery_eligible':False,
              'limitations':['Baseline preflight only; this does not verify business existence or approve customer delivery.',
                             'Last-verification check tests presence only; format, freshness and evidence must be verified during review.',
                             'Source permissions, matching, independent QC, profanity/relationship checks and export gates remain outstanding.']}
    run = PocPreflightRun(dataset_id=dataset_id, report=report)
    db.add(run)
    db.commit()
    return {'id':run.id, **report}


@router.get('/datasets/{dataset_id}/preflights')
def preflight_history(dataset_id: UUID, db: Session = Depends(storage)):
    get_dataset(db, dataset_id)
    runs = db.scalars(select(PocPreflightRun).where(PocPreflightRun.dataset_id==dataset_id)
                      .order_by(PocPreflightRun.created_at.desc()).limit(10)).all()
    return [{'id':r.id, **r.report} for r in runs]
