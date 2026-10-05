from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiKey, GenerationJob
from ..novelai import ImageParameters
from ..services import submit_job
from .deps import downstream_key
from .user import image_path, job_view


router = APIRouter(prefix='/v1', tags=['generation'])


class ImageRequest(BaseModel):
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=4000)
    size: str = Field(default='1024x1024', pattern=r'^\d{2,5}x\d{2,5}$')
    n: int = Field(default=1, ge=1, le=1)
    parameters: ImageParameters = Field(default_factory=ImageParameters)


@router.post('/images/generations', status_code=202)
def generate(
    payload: ImageRequest,
    idempotency_key: str = Header(min_length=1, max_length=150, alias='Idempotency-Key'),
    api_key: ApiKey = Depends(downstream_key),
    db: Session = Depends(get_db),
) -> dict:
    job = submit_job(db, api_key, payload.model, payload.prompt, payload.size,
                     idempotency_key, payload.parameters)
    return job_view(job)


@router.get('/jobs/{job_id}')
def get_job(job_id: str, api_key: ApiKey = Depends(downstream_key), db: Session = Depends(get_db)) -> dict:
    job = db.get(GenerationJob, job_id)
    if job is None or job.user_id != api_key.user_id:
        raise HTTPException(404, 'Job not found')
    return job_view(job)


@router.get('/jobs/{job_id}/image')
def get_job_image(job_id: str, api_key: ApiKey = Depends(downstream_key),
                  db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    image = image_path(job_id)
    if job is None or job.user_id != api_key.user_id or job.status != 'succeeded' or image is None:
        raise HTTPException(404, 'Image not found')
    return FileResponse(image, media_type='image/png' if image.suffix == '.png' else 'image/jpeg', filename=image.name)
