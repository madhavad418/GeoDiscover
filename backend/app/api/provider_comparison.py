"""HERE baseline vs a Google/Grab provider extract: New / Update / Delete / Matched / Review, held in memory."""
import threading
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..models.customer import CustomerPoi
from ..models.platform import User
from ..services import provider_comparison as service
from .customer import get_dataset, storage

router = APIRouter(prefix='/provider-comparison', tags=['HERE vs provider extract'])
operator = require_roles('ops_manager', 'qc_lead')
LOCK = threading.RLock()
JOBS = {}
TTL = 6 * 3600
MAX_UPLOAD = 50 * 1024 * 1024
# Columns the page table shows per list; the Excel file carries every column.
TABLE = {
    'new': ['name1', 'primarycategorynm', 'upaddress', 'phone_numbers', 'webaddress', 'sources', 'reason'],
    'update': ['here_placeid', 'name1', 'primarycategorynm', 'changed_fields', 'sources', 'distance_m', 'reason'],
    'delete': ['here_placeid', 'name1', 'primarycategorynm', 'upaddress', 'delete_basis'],
    'matched': ['here_placeid', 'name1', 'primarycategorynm', 'sources', 'distance_m', 'match_level'],
    'review': ['name1', 'primarycategorynm', 'sources', 'candidate_here_names', 'reason'],
}


def _expire():
    now = time.time()
    for key in [k for k, j in JOBS.items() if j['state'] != 'running' and now - j.get('finished_at', j['created']) > TTL]:
        del JOBS[key]


def _public(job):
    return {k: job[k] for k in ('id', 'state', 'aoi', 'dataset_id', 'dataset', 'extract', 'created', 'error', 'stats')} | {
        'labels': service.KINDS, 'columns': TABLE}


def _job(run_id, user):
    with LOCK:
        job = JOBS.get(str(run_id))
        if not job or job['owner'] != str(user.id):
            raise HTTPException(404, 'Comparison not found. It may have expired; run it again.')
        return job


def _work(job, here_rows, extract, country):
    try:
        lists, stats = service.run(here_rows, extract, country, job['dataset_id'])
        with LOCK:
            job.update(lists=lists, stats=stats, state='finished')
    except Exception as exc:  # surfaced to the page; the request that started the job has already returned
        with LOCK:
            job.update(state='failed', error=f'Comparison failed: {exc}')
    finally:
        with LOCK:
            job['finished_at'] = time.time()


@router.post('/runs', status_code=202)
def start(dataset_id: UUID = Form(...), file: UploadFile = File(...), db: Session = Depends(storage), user: User = Depends(operator)):
    dataset = get_dataset(db, dataset_id)
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, 'The provider extract is larger than 50 MB.')
    try:
        extract = service.read_extract(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    here_rows = [dict(r._mapping) for r in db.execute(select(
        CustomerPoi.id, CustomerPoi.place_id, CustomerPoi.name, CustomerPoi.category_code, CustomerPoi.category_name,
        CustomerPoi.latitude, CustomerPoi.longitude, CustomerPoi.address, CustomerPoi.raw).where(CustomerPoi.dataset_id == dataset.id))]
    if not service.overlaps(here_rows, extract):
        raise HTTPException(422, f'This extract does not cover {dataset.aoi}: most of its POIs are outside the HERE baseline area. '
                                 'Choose the extract collected for this area.')
    with LOCK:
        _expire()
        if any(j['state'] == 'running' for j in JOBS.values()):
            raise HTTPException(409, 'Another comparison is running. Try again when it finishes.')
        job = {'id': str(uuid4()), 'owner': str(user.id), 'state': 'running', 'aoi': dataset.aoi, 'dataset_id': str(dataset.id),
               'dataset': dataset.filename, 'extract': file.filename, 'created': time.time(), 'error': None, 'stats': None, 'lists': None}
        JOBS[job['id']] = job
    threading.Thread(target=_work, args=(job, here_rows, extract, dataset.country), daemon=True).start()
    return _public(job)


@router.get('/runs/{run_id}')
def status(run_id: UUID, response: Response, user: User = Depends(operator)):
    response.headers['Cache-Control'] = 'no-store'
    with LOCK:
        return _public(_job(run_id, user))


def _finished(run_id, user):
    job = _job(run_id, user)
    if job['state'] != 'finished':
        raise HTTPException(409, 'The comparison has not finished.')
    return job


@router.get('/runs/{run_id}/rows')
def rows(run_id: UUID, kind: str = Query(..., pattern='^(new|update|delete|matched|review)$'), q: str = Query('', max_length=100),
         basis: str = Query('', max_length=40), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
         user: User = Depends(operator)):
    items = _finished(run_id, user)['lists'][kind]
    if basis:
        items = [r for r in items if r.get('delete_basis') == basis]
    if q.strip():
        needle = q.strip().lower()
        items = [r for r in items if needle in ' '.join(str(r.get(c, '')) for c in TABLE[kind] + ['placeid']).lower()]
    page = items[offset:offset + limit]
    return {'total': len(items), 'offset': offset, 'columns': TABLE[kind],
            'rows': [{c: r.get(c, '') for c in TABLE[kind]} | {'_lat': r['_lat'], '_lon': r['_lon'],
                                                                '_index': offset + i} for i, r in enumerate(page)]}


@router.get('/runs/{run_id}/rows/{kind}/{index}')
def row(run_id: UUID, kind: str, index: int, user: User = Depends(operator)):
    items = _finished(run_id, user)['lists'].get(kind)
    if items is None or not 0 <= index < len(items):
        raise HTTPException(404, 'Row not found.')
    return service.public_row({k: v for k, v in items[index].items() if v not in ('', None)})


@router.get('/runs/{run_id}/map')
def points(run_id: UUID, user: User = Depends(operator)):
    lists = _finished(run_id, user)['lists']
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['_lon'], r['_lat']]},
         'properties': {'kind': kind, 'index': i, 'name': r.get('name1', ''), 'category': r.get('primarycategorynm', '')}}
        for kind, items in lists.items() for i, r in enumerate(items)]}


@router.get('/runs/{run_id}/excel')
def excel(run_id: UUID, user: User = Depends(operator)):
    job = _finished(run_id, user)
    content = service.workbook(job['lists'], job['stats'], {'aoi': job['aoi'], 'dataset': job['dataset'], 'extract': job['extract']})
    name = f"{job['aoi'].replace(' ', '_')}_HERE_comparison_New_Update_Delete.xlsx"
    return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Cache-Control': 'no-store', 'Content-Disposition': f'attachment; filename="{name}"'})
