import logging
import time

import httpx

from .config import get_settings
from .db import SessionLocal
from .models import UpstreamAccount
from .services import claim_job, finish_job, recover_expired
from .upstream import NovelAIImageAdapter, OpenAIImageAdapter, UpstreamUncertain


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_once(job_id: str | None = None) -> bool:
    settings = get_settings()
    with SessionLocal() as db:
        recovered = recover_expired(db)
        if recovered:
            logger.warning('Marked %s expired jobs for reconciliation', recovered)
        job = claim_job(db, settings.job_lease_seconds, job_id)
        if job is None:
            return False
        job_id = job.id
        account = db.get(UpstreamAccount, job.upstream_account_id)
        if account is None or not account.enabled:
            db.rollback()
            finish_job(db, job_id, None, 'Upstream account disabled')
            return True
        adapter_class = NovelAIImageAdapter if account.provider == 'novelai' else OpenAIImageAdapter
        adapter = adapter_class(account, settings.upstream_timeout_seconds)
        try:
            result = adapter.generate(job)
            error = None
            uncertain = False
        except UpstreamUncertain as exc:
            result, error, uncertain = None, str(exc), True
        except (httpx.HTTPStatusError, ValueError) as exc:
            result, error, uncertain = None, str(exc)[:500], False
        except Exception:
            logger.exception('Unexpected upstream response for job %s', job.id)
            result, error, uncertain = None, 'Unexpected upstream result; inspect logs', True
        db.rollback()
        finish_job(db, job_id, result, error, uncertain)
        logger.info('Finished job %s; uncertain=%s', job_id, uncertain)
        return True


def main() -> None:
    while True:
        try:
            if not run_once():
                time.sleep(get_settings().job_poll_seconds)
        except Exception:
            logger.exception('Worker iteration failed')
            time.sleep(get_settings().job_poll_seconds)


if __name__ == '__main__':
    main()
