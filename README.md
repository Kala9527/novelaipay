# Novelaipay

FastAPI + React/Vite/TypeScript image API console with NovelAI and OpenAI-compatible upstreams. The API and worker share one Python 3.13 image; PostgreSQL stores jobs, accounts, balances and immutable ledger entries. SQLite is supported for local debugging. The built frontend is served by FastAPI on port **8009**.

## Local development (Windows)

```powershell
& 'D:\miniconda3\shell\condabin\conda-hook.ps1'
conda activate 'D:\miniconda3_envs\novelaipay'
python -m pip install -r backend\requirements.txt
npm ci --prefix frontend
Copy-Item .env.example .env
Copy-Item config.example.yaml config.yaml
# Edit .env (secrets/DB) and config.yaml (admin account/registration).
# For local SQLite use DATABASE_URL=sqlite:///./dev.db and COOKIE_SECURE=false.
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

`config.yaml` is ignored by Git. Its `admin` section is the source of truth for the single administrator's email, display name, password and concurrent job limit. Re-run `python -m app.bootstrap` after changing it locally; Compose runs bootstrap when the API starts. Users can self-register when `registration.enabled` is true, or an administrator can add them. Administrator deletion is blocked; ordinary user deletion archives the account and preserves its balance, ledger and job history. The administrator can restore an archived account, then issue new API keys.

See [开发部署文档.md](开发部署文档.md) for the Ubuntu VM, production image transfer, API examples and troubleshooting.

For NovelAI, add an upstream account with provider `novelai`, base URL `https://image.novelai.net`, and an Access Token. Map a public model to `nai-diffusion-4-5-full` (or another supported model) and configure CNY per Anlas. A downstream key submits jobs through `/v1/images/generations`; the worker settles against the upstream account's actual Anlas balance change. Use a dedicated upstream account and see the deployment document for pricing limits and image retrieval.
