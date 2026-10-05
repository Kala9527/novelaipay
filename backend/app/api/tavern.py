"""Synchronous OpenAI-style image endpoint for Tavern Scene Plugin 1.2.2."""

import base64
import io
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..config import get_settings
from ..models import ApiKey, GenerationJob, JobStatus, ModelMapping, PriceVersion, UpstreamAccount, User
from ..novelai import ImageParameters
from ..services import submit_job
from .user import image_path
from ..worker import run_once
from .deps import downstream_key


router = APIRouter(tags=['tavern'])


def character_item(item: dict) -> dict:
    center = item.get('center') if item.get('center') is not None else item.get('centers') or item.get('position') or {}
    if isinstance(center, list):
        center = center[0] if center else {}
    if isinstance(center, str) and len(center) == 2 and center[0].upper() in 'ABCDE' and center[1] in '12345':
        center = {'x': ('ABCDE'.index(center[0].upper()) + 0.5) / 5,
                  'y': (int(center[1]) - 0.5) / 5}
    if not isinstance(center, dict):
        center = {'x': center}
    prompt = item.get('prompt') or item.get('char_caption') or item.get('tag') or item.get('tags') or ''
    if isinstance(prompt, list):
        prompt = ', '.join(str(tag) for tag in prompt)
    return {'prompt': prompt, 'negative_prompt': item.get('negative_prompt') or
            item.get('negative') or item.get('uc') or '',
            'center': center.get('x', item.get('x', 0.5)),
            'top': center.get('y', item.get('top', item.get('y', 0.5)))}


def normalize_request(body: dict) -> tuple[str, str, str, ImageParameters]:
    model = body.get('model')
    prompt = body.get('prompt') or body.get('input') or body.get('tag')
    if not isinstance(model, str) or not model or not isinstance(prompt, str) or not prompt:
        raise HTTPException(422, 'Model and prompt are required')
    if body.get('n', body.get('n_samples', 1)) != 1:
        raise HTTPException(422, 'Only one image per request is supported')
    size = body.get('size')
    presets = {'方图': '1024x1024', '横图': '1216x832', '竖图': '832x1216',
               'square': '1024x1024', 'landscape': '1216x832', 'portrait': '832x1216'}
    if isinstance(size, str) and size in presets:
        size = presets[size]
    elif not isinstance(size, str) or 'x' not in size.lower():
        size = f"{body.get('width', 1024)}x{body.get('height', 1024)}"
    addition = body.get('addition') or {}
    if not isinstance(addition, dict):
        raise HTTPException(422, 'Invalid addition')
    incoming = body.get('parameters') if isinstance(body.get('parameters'), dict) else {}
    incoming = {**body, **incoming}
    aliases = {
        'steps': ('steps',), 'scale': ('scale', 'cfg_scale', 'cfg'),
        'sampler': ('sampler',), 'negative_prompt': ('negative_prompt', 'negativePrompt', 'uc', 'negative'),
        'seed': ('seed',), 'quality_toggle': ('quality_toggle', 'qualityToggle'),
        'smea': ('smea', 'sm'), 'smea_dyn': ('smea_dyn', 'sm_dyn'),
        'cfg_rescale': ('cfg_rescale', 'cfg'), 'noise_schedule': ('noise_schedule',),
        'dynamic_thresholding': ('dynamic_thresholding', 'decrisper'),
        'variety_boost': ('variety_boost', 'variety'),
        'skip_cfg_above_sigma': ('skip_cfg_above_sigma',),
        'strength': ('strength', 'i2iforce'),
        'noise': ('noise', 'i2icl'),
    }
    parameters = {}
    for name, options in aliases.items():
        for option in options:
            if option in incoming and incoming[option] is not None:
                parameters[name] = incoming[option]
                break
    if parameters.get('seed') in (-1, '-1'):
        parameters.pop('seed')
    image = (addition.get('imageToImageBase64') or addition.get('imageBase64') or
             body.get('image') or body.get('imageBase64'))
    mask = body.get('mask') or addition.get('mask')
    if image:
        parameters['image'] = image
        parameters['action'] = 'infill' if mask else 'img2img'
    if mask:
        parameters['mask'] = mask
    if 'i2iforce' in addition and 'inpaintStrength' not in body:
        parameters['strength'] = addition['i2iforce']
    if 'i2icl' in addition:
        parameters['noise'] = addition['i2icl']
    if body.get('inpaintStrength') is not None:
        parameters['inpaint_img2img_strength'] = body['inpaintStrength']
    references = addition.get('vibeTransferList') or []
    if not isinstance(references, list):
        raise HTTPException(422, 'Invalid reference list')
    parameters['references'] = [{'image': item.get('base64'),
                                 'information_extracted': item.get('infoExtract', 1),
                                 'strength': item.get('refStrength', 0.6)} for item in references]
    keep = addition.get('characterKeep')
    if isinstance(keep, dict) and keep.get('base64'):
        parameters['precise_reference'] = {'image': keep['base64'],
            'description': 'character&style' if keep.get('keepVibe', True) else 'character',
            'strength': keep.get('strength', 1), 'fidelity': keep.get('fidelity', 1)}
    roles = addition.get('multiRoleList') or []
    if not isinstance(roles, list):
        raise HTTPException(422, 'Invalid character list')
    if any(not isinstance(item, dict) for item in roles):
        raise HTTPException(422, 'Invalid character list')
    parameters['character_prompts'] = [character_item(item) for item in roles if item.get('enabled', True)]
    try:
        return model, prompt, size, ImageParameters.model_validate(parameters)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_input=False, include_context=False)) from exc


@router.get('/v1/models')
@router.get('/models')
@router.get('/genarate/models')
@router.get('/genarate/v1/models')
def tavern_models(_: ApiKey = Depends(downstream_key), db: Session = Depends(get_db)) -> dict:
    mappings = db.scalars(select(ModelMapping).where(ModelMapping.enabled.is_(True)).order_by(
        ModelMapping.public_name)).all()
    return {'object': 'list', 'data': [
        {'id': mapping.public_name, 'object': 'model', 'owned_by': 'novelaipay'}
        for mapping in mappings]}


def wait_for_image(db: Session, job_id: str) -> tuple[GenerationJob, bytes]:
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        db.expire_all()
        job = db.get(GenerationJob, job_id)
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.UNCERTAIN):
            break
        if job.status == JobStatus.QUEUED:
            run_once(job_id)
        time.sleep(0.3)
    db.expire_all()
    job = db.get(GenerationJob, job_id)
    if job.status == JobStatus.UNCERTAIN:
        raise HTTPException(503, f'Generation requires reconciliation; job {job_id}')
    if job.status != JobStatus.SUCCEEDED:
        raise HTTPException(502 if job.status == JobStatus.FAILED else 504,
                            job.error or f'Generation incomplete; job {job_id}')
    image = image_path(job_id)
    if image is None:
        raise HTTPException(502, 'Generated image missing from local storage')
    return job, image.read_bytes()


@router.post('/genarate')
@router.post('/generate', include_in_schema=False)
def tavern_generate(body: dict, request: Request, api_key: ApiKey = Depends(downstream_key),
                    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
                    db: Session = Depends(get_db)) -> dict:
    model, prompt, size, parameters = normalize_request(body)
    job = submit_job(db, api_key, model, prompt, size, idempotency_key or str(uuid.uuid4()), parameters)
    job, image = wait_for_image(db, job.id)
    encoded = base64.b64encode(image).decode('ascii')
    now = datetime.now(timezone.utc)
    image_token = jwt.encode({
        'type': 'tavern_image', 'sub': job.id, 'user_id': api_key.user_id,
        'iat': now, 'exp': now + timedelta(minutes=15),
    }, get_settings().app_secret_key, algorithm='HS256')
    image_url = str(request.url_for('tavern_image', job_id=job.id).include_query_params(token=image_token))
    return {'created': int(job.created_at.timestamp()), 'model': model,
            'url': image_url, 'image_url': image_url,
            'data': [{'url': image_url, 'b64_json': encoded}], 'images': [image_url],
            'image': image_url, 'job_id': job.id, 'anlas_charged': job.anlas_cost,
            'amount': str(job.reserved_amount)}


@router.get('/genarate/images/{job_id}', name='tavern_image', include_in_schema=False)
def tavern_image(job_id: str, token: str, db: Session = Depends(get_db)):
    try:
        claims = jwt.decode(token, get_settings().app_secret_key, algorithms=['HS256'])
    except jwt.InvalidTokenError as exc:
        raise HTTPException(404, 'Image not found') from exc
    job = db.get(GenerationJob, job_id)
    image = image_path(job_id)
    if (claims.get('type') != 'tavern_image' or claims.get('sub') != job_id or
            job is None or job.user_id != claims.get('user_id') or
            job.status != JobStatus.SUCCEEDED or image is None):
        raise HTTPException(404, 'Image not found')
    return FileResponse(image, media_type='image/png' if image.suffix == '.png' else 'image/jpeg', filename=image.name)


def raw_novelai_request(body: dict, db: Session) -> tuple[str, str, str, ImageParameters]:
    if body.get('action', 'generate') not in {'generate', 'img2img', 'infill'}:
        raise HTTPException(422, 'Unsupported image action')
    incoming = body.get('parameters')
    if not isinstance(incoming, dict):
        raise HTTPException(422, 'NovelAI parameters are required')
    if incoming.get('n_samples', 1) != 1:
        raise HTTPException(422, 'Only one image per request is supported')
    model_name = body.get('model')
    prompt = body.get('input')
    if not isinstance(model_name, str) or not model_name or not isinstance(prompt, str) or not prompt:
        raise HTTPException(422, 'Model and input are required')
    mapping = db.scalar(select(ModelMapping).where(
        ModelMapping.public_name == model_name, ModelMapping.enabled.is_(True)))
    if mapping is None:
        matches = db.scalars(select(ModelMapping).where(
            ModelMapping.upstream_model == model_name, ModelMapping.enabled.is_(True)
        ).order_by(ModelMapping.id)).all()
        if not matches:
            raise HTTPException(404, 'Model unavailable')
        mapping = matches[0]
    account = db.get(UpstreamAccount, mapping.upstream_account_id)
    if account is None or account.provider != 'novelai':
        raise HTTPException(422, 'Model is not a NovelAI model')
    width, height = incoming.get('width'), incoming.get('height')
    if not isinstance(width, int) or not isinstance(height, int):
        raise HTTPException(422, 'Width and height are required')
    negative = incoming.get('negative_prompt')
    if negative is None and isinstance(incoming.get('v4_negative_prompt'), dict):
        negative = incoming['v4_negative_prompt'].get('caption', {}).get('base_caption')
    params = {
        'steps': incoming.get('steps', 23), 'scale': incoming.get('scale', 4),
        'sampler': incoming.get('sampler', 'k_euler_ancestral'),
        'negative_prompt': negative or '', 'seed': incoming.get('seed'),
        'quality_toggle': incoming.get('qualityToggle', False),
        'smea': incoming.get('sm', False), 'smea_dyn': incoming.get('sm_dyn', False),
        'cfg_rescale': incoming.get('cfg_rescale', 0),
        'noise_schedule': incoming.get('noise_schedule', 'karras'),
        'dynamic_thresholding': incoming.get('dynamic_thresholding', False),
        'skip_cfg_above_sigma': incoming.get('skip_cfg_above_sigma'),
        'action': body.get('action', 'generate'), 'image': incoming.get('image'),
        'mask': incoming.get('mask'), 'strength': incoming.get('strength', 0.7),
        'noise': incoming.get('noise', 0),
        'inpaint_img2img_strength': incoming.get('inpaintImg2ImgStrength'),
    }
    images = incoming.get('reference_image_multiple') or []
    info = incoming.get('reference_information_extracted_multiple') or []
    strengths = incoming.get('reference_strength_multiple') or []
    if len(images) != len(info) or len(images) != len(strengths):
        raise HTTPException(422, 'Reference parameter lengths differ')
    params['references'] = [{'image': image, 'information_extracted': info[index],
                             'strength': strengths[index]} for index, image in enumerate(images)]
    chars = incoming.get('characterPrompts') or []
    if chars:
        params['character_prompts'] = [character_item(item) for item in chars if item.get('enabled', True)]
    else:
        chars = (incoming.get('v4_prompt') or {}).get('caption', {}).get('char_captions', [])
        negatives = (incoming.get('v4_negative_prompt') or {}).get('caption', {}).get('char_captions', [])
        params['character_prompts'] = [
            {**character_item(item), 'negative_prompt': negatives[index].get('char_caption', '')
             if index < len(negatives) else ''}
            for index, item in enumerate(chars)
        ]
    precise = incoming.get('director_reference_images') or []
    if precise:
        description = (incoming.get('director_reference_descriptions') or [{}])[0]
        params['precise_reference'] = {'image': precise[0],
            'information_extracted': (incoming.get('director_reference_information_extracted') or [1])[0],
            'strength': (incoming.get('director_reference_strength_values') or [1])[0],
            'fidelity': (incoming.get('director_reference_secondary_strength_values') or [1])[0],
            'description': description.get('caption', {}).get('base_caption', 'character&style')}
    try:
        return mapping.public_name, prompt, f'{width}x{height}', ImageParameters.model_validate(params)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_input=False, include_context=False)) from exc


@router.post('/ai/generate-image')
@router.post('/genarate/ai/generate-image', include_in_schema=False)
def novelai_proxy_generate(body: dict, api_key: ApiKey = Depends(downstream_key),
                           idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
                           db: Session = Depends(get_db)) -> Response:
    model, prompt, size, parameters = raw_novelai_request(body, db)
    job = submit_job(db, api_key, model, prompt, size, idempotency_key or str(uuid.uuid4()), parameters)
    _, image = wait_for_image(db, job.id)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr('image_0.png', image)
    return Response(archive.getvalue(), media_type='application/zip',
                    headers={'X-Job-Id': job.id})


@router.get('/user/subscription')
@router.get('/genarate/user/subscription', include_in_schema=False)
def novelai_proxy_subscription(api_key: ApiKey = Depends(downstream_key),
                                db: Session = Depends(get_db)) -> dict:
    user = db.get(User, api_key.user_id)
    prices = db.scalars(select(PriceVersion).join(ModelMapping).join(UpstreamAccount).where(
        ModelMapping.enabled.is_(True), UpstreamAccount.provider == 'novelai',
        PriceVersion.billing_mode == 'anlas').order_by(PriceVersion.id)).all()
    latest = {}
    for price in prices:
        latest[price.model_mapping_id] = price
    rate = min((price.amount for price in latest.values()), default=Decimal('1'))
    available = max(Decimal('0'), user.balance - user.reserved)
    anlas = int(available / rate) if rate > 0 else 0
    return {'tier': 3, 'trainingStepsLeft': {
        'fixedTrainingStepsLeft': anlas, 'purchasedTrainingSteps': 0}}
