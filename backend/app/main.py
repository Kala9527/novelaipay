from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, auth, generation, payment, user, tavern
from .config import get_settings


app = FastAPI(title='Novelaipay', version='0.2.0')
app.add_middleware(CORSMiddleware,
                   allow_origins=[origin.strip() for origin in get_settings().cors_allowed_origins.split(',')
                                  if origin.strip()],
                   allow_methods=['GET', 'POST', 'OPTIONS'],
                   allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'])
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(payment.router)
app.include_router(generation.router)
app.include_router(tavern.router)


@app.get('/healthz')
def healthz() -> dict:
    return {'status': 'ok'}


dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if dist.exists():
    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')


@app.get('/{path:path}', include_in_schema=False)
def spa(path: str):
    if path.startswith(('api/', 'v1/', 'assets/', 'genarate/', 'ai/', 'user/')):
        raise HTTPException(404, 'Not found')
    index = dist / 'index.html'
    if not index.exists():
        raise HTTPException(404, 'Frontend has not been built')
    return FileResponse(index)
