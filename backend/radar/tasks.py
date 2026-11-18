"""Jobs programados con Celery + Redis.

Flujo por tienda (cada SCRAPE_EVERY_HOURS horas, vía Celery beat):

    scrape_store ──> process_snapshot ──> (cuando terminan todas) refresh_and_alert

- `scrape_store` tiene reintentos con backoff exponencial y jitter para
  errores transitorios (429, 5xx, timeouts, rate limit local).
- `rate_limit` de Celery limita por worker; el límite global por dominio
  vive en Redis (ver radar.http).
- `acks_late` + tareas idempotentes: si un worker muere a mitad de camino,
  la tarea se re-entrega y re-ejecutarla no duplica datos.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from celery import Celery, chain, chord
from celery.schedules import crontab

from .config import settings
from .http import RateLimited, RetryableHTTPError

log = logging.getLogger(__name__)

app = Celery("radar", broker=settings.redis_url, backend=settings.redis_url)
app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_expires=3600,
    timezone="America/Santiago",
    beat_schedule={
        "scrape-all": {
            "task": "radar.tasks.scrape_all",
            "schedule": crontab(minute=0, hour=f"*/{settings.scrape_cron_hours}"),
        },
    },
)


@app.task(
    bind=True,
    autoretry_for=(httpx.TransportError, RetryableHTTPError),
    retry_backoff=30,
    retry_backoff_max=900,
    retry_jitter=True,
    max_retries=5,
    rate_limit="6/m",
)
def scrape_store(self, store_slug: str, day: str | None = None) -> int:
    from .db import SessionLocal
    from .etl import store_snapshot
    from .sources import get_source

    observed = date.fromisoformat(day) if day else date.today()
    try:
        listings = get_source(store_slug).fetch(observed)
    except RateLimited as exc:
        raise self.retry(exc=exc, countdown=exc.wait_s) from exc
    with SessionLocal.begin() as session:
        snapshot_id = store_snapshot(session, store_slug, observed, listings)
    log.info("scrape %s: %d fichas -> snapshot %s", store_slug, len(listings), snapshot_id)
    return snapshot_id


@app.task(bind=True, max_retries=3, default_retry_delay=60, acks_late=True)
def process_snapshot(self, snapshot_id: int) -> dict:
    from .db import SessionLocal
    from .etl import process_snapshot as run

    try:
        with SessionLocal.begin() as session:
            return run(session, snapshot_id).__dict__
    except Exception as exc:  # p. ej. la API de embeddings no responde
        raise self.retry(exc=exc) from exc


@app.task
def refresh_and_alert(_results=None) -> int:
    from .alerts import evaluate_alerts
    from .db import SessionLocal, refresh_stats

    refresh_stats()
    with SessionLocal.begin() as session:
        return evaluate_alerts(session)


@app.task
def scrape_all(day: str | None = None) -> str:
    from .sources import STORES

    # Los scrapers corren en paralelo, pero el ETL va a la cola "etl", que se
    # consume con concurrencia 1: si dos ETL crearan a la vez el mismo producto
    # nuevo desde dos tiendas, quedaría duplicado. Las alertas corren al final.
    header = [chain(scrape_store.s(slug, day), process_snapshot.s().set(queue="etl")) for slug in STORES]
    return chord(header)(refresh_and_alert.s().set(queue="etl")).id
