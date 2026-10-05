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

`config.yaml` is ignored by Git. Its `admin` section is the source of truth for the single administrator's email, display name and password. Re-run `python -m app.bootstrap` after changing it locally; Compose runs bootstrap when the API starts. Users can self-register when `registration.enabled` is true, or an administrator can add them. Administrator deletion is blocked; ordinary user deletion archives the account and preserves its balance, ledger and job history. The administrator can restore an archived account, then issue new API keys.

Create upstream accounts, then groups containing one or more accounts. Publish models and prices separately in each group; each model can map to a different upstream model name on each account. Both group and account capacity default to 10 running jobs. Downstream keys are scoped to one group, and multiple keys may use the same group. `/genarate` and `/v1/images/generations` accept a model from the key's group; `/v1/models` lists the models visible to that key. OpenAI-compatible account model lists are fetched from the upstream `/models` endpoint. NovelAI does not expose a model-list endpoint, so the console offers supported names and manual entry. Dates and date filters in the console use Beijing time. Administrators can filter and hide usage and billing rows; wallet balances and audit data remain unchanged.

The worker prefers an idle account in the group and retries another account after a definite 401, 403, 404 or 429 response. A timeout or ambiguous upstream result is held for reconciliation to avoid duplicate charges. NovelAI bills from account balance changes, so overlapping generations on the same NovelAI account are also held for reconciliation rather than assigned an unreliable Anlas amount.

See [开发部署文档.md](开发部署文档.md) for the Ubuntu VM, production image transfer, API examples and troubleshooting.

For NovelAI, add an upstream account with provider `novelai`, base URL `https://image.novelai.net`, and an Access Token. Map a public model to `nai-diffusion-4-5-full` (or another supported model) and configure CNY per Anlas. A downstream key submits jobs through `/v1/images/generations`; the worker settles against the upstream account's actual Anlas balance change. Use a dedicated upstream account and see the deployment document for pricing limits and image retrieval.

### Tavern Scene Plugin 1.2.2

In the plugin's image generation settings, choose **NovelAI**, then the **third-party proxy** channel. Set the proxy URL to `http://127.0.0.1:8009/genarate` (or the port where this API is running), the API key to a downstream `pst-` key, and the model to an enabled public model such as `nai-diffusion-4-5-full`. The plugin's streaming proxy option is supported. The service returns a short-lived signed image URL that the plugin downloads immediately.

NovelAI requests are billed at the configured CNY-per-Anlas rate using the upstream account's actual Anlas balance change, plus a per-generation surcharge that defaults to CNY 0.1. For example, at CNY 0.1 per Anlas, a generation charged zero Anlas upstream costs CNY 0.1 downstream. Size, steps and supported model options can affect the Anlas charge. SMEA is ignored for NovelAI V4/V5 models, which do not support it. The initial reservation is an estimate and is released or adjusted on completion. Text-to-image, image-to-image, inpainting, Vibe transfer, precise reference and multi-character prompts are supported. The native NovelAI proxy route `/ai/generate-image` returns the official ZIP image format.

NovelAI's [subscription and Anlas rules](https://docs.novelai.net/en/subscription/) and [image generation basics](https://docs.novelai.net/en/image/basics/) are the reference for free-generation conditions. The project settles from the real upstream balance difference because NovelAI does not publish a complete current price formula.
