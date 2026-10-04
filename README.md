# Novelaipay

FastAPI + React/Vite/TypeScript image API console. The API and worker share one Python 3.13 image; PostgreSQL stores jobs, accounts, balances and immutable ledger entries. The built frontend is served by FastAPI on port **8009**.

## Local development (Windows)

```powershell
& 'D:\miniconda3\shell\condabin\conda-hook.ps1'
conda activate 'D:\miniconda3_envs\novelaipay'
python -m pip install -r backend\requirements.txt
npm ci --prefix frontend
Copy-Item .env.example .env
# Edit .env; for local SQLite use DATABASE_URL=sqlite:///./dev.db and COOKIE_SECURE=false.
cd backend
alembic upgrade head
python -m app.bootstrap
python -m uvicorn app.main:app --host 127.0.0.1 --port 8009
```

For frontend editing, run `npm run dev --prefix frontend` in a second terminal. Vite proxies API calls to port 8009. To serve the compiled frontend from FastAPI, run `npm run build --prefix frontend` and open `http://127.0.0.1:8009`.

Set `UPSTREAM_KEY_ENCRYPTION_KEY` to a Fernet key generated with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

See [开发部署文档.md](开发部署文档.md) for the Ubuntu VM, production image transfer, API examples and troubleshooting.
