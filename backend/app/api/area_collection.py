import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..auth import require_roles
from ..models.platform import User
from ..services import area_collection as service

router = APIRouter(prefix='/area-collection',tags=['AOI provider collection'])
operator = require_roles('ops_manager','qc_lead')


class CollectionRequest(BaseModel):
    name: str = Field(default='Uploaded AOI',max_length=160)
    geometry: dict
    queries: list[str] | None = Field(default=None,min_length=1,max_length=500)
    budget_per_provider: int = Field(default=100,ge=1,le=1000)
    grid_metres: int = Field(default=500,ge=100,le=2000)
    language: str = Field(default='',max_length=20,pattern=r'^[a-zA-Z-]*$')


@router.get('/options')
def options(_: User = Depends(operator)):
    return {'queries':service.default_queries(),'columns':service.HEADERS,'maximum_requests_per_provider':1000}


@router.post('/runs',status_code=202)
def create(body: CollectionRequest,user: User = Depends(operator)):
    queries = list(dict.fromkeys(q.strip() for q in (body.queries or service.default_queries()) if q.strip()))
    if not queries or any(len(q)>150 for q in queries):
        raise HTTPException(422,'Use nonempty search terms of at most 150 characters each.')
    try:
        return service.start(user.id,body.name,body.geometry,queries,body.budget_per_provider,body.grid_metres,body.language)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None


def owned(run_id,user):
    with service.LOCK:
        job=service.JOBS.get(str(run_id))
        if not job or job['owner']!=str(user.id): raise HTTPException(404,'Collection run not found.')
        if job['state']!='running' and time.time()-job.get('finished_at',job['created'])>service.TTL:
            del service.JOBS[str(run_id)]
            raise HTTPException(410,'This temporary collection has expired. Start a new run.')
        return job


@router.get('/runs/{run_id}')
def status(run_id:UUID,response:Response,user:User=Depends(operator)):
    response.headers['Cache-Control']='no-store'
    return service.public(owned(run_id,user))


@router.post('/runs/{run_id}/cancel')
def cancel(run_id:UUID,user:User=Depends(operator)):
    job=owned(run_id,user); job['cancel'].set()
    return service.public(job)


@router.get('/runs/{run_id}/excel')
def excel(run_id:UUID,user:User=Depends(operator)):
    job=owned(run_id,user)
    if job['state']=='running': raise HTTPException(409,'Wait for the run to finish or cancel it before downloading.')
    return Response(service.workbook(job),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Cache-Control':'no-store','Content-Disposition':f'attachment; filename="JSAN_provider_extract_{run_id}.xlsx"'})
