"""Comandos de mantenimiento.

python -m radar.cli init                 # crea extensión, tablas y vistas
python -m radar.cli backfill --days 120  # historial simulado (síncrono, reanudable)
python -m radar.cli scrape               # encola un scraping de todas las tiendas (Celery)
python -m radar.cli run                  # mismo pipeline, síncrono y sin cola (cron de GitHub Actions)
python -m radar.cli alerts               # evalúa alertas ahora
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta

from sqlalchemy import text

from .db import SessionLocal, init_db, refresh_stats
from .etl import process_snapshot, store_snapshot
from .sources import STORES, get_source


def backfill(days: int, end: date | None = None) -> None:
    """Carga `days` días de historial ejecutando el mismo ETL que la cola.

    Reanudable: se salta los pares (tienda, día) que ya tienen snapshot, así
    que si se corta a mitad de camino basta con volver a ejecutarlo.
    """
    end = end or date.today()
    t0 = time.perf_counter()
    totals = {"observations": 0, "new_products": 0, "new_listings": 0}
    with SessionLocal() as session:
        done = set(
            session.execute(
                text("SELECT s.slug, r.observed_on FROM raw_snapshots r JOIN stores s ON s.id = r.store_id")
            ).all()
        )
    skipped = 0
    for i in range(days, -1, -1):
        day = end - timedelta(days=i)
        pending = [slug for slug in STORES if (slug, day) not in done]
        skipped += len(STORES) - len(pending)
        if not pending:
            continue
        with SessionLocal.begin() as session:  # un commit por día: el avance queda guardado
            for slug in pending:
                snap_id = store_snapshot(session, slug, day, get_source(slug, "simulated").fetch(day))
                r = process_snapshot(session, snap_id)
                for k in totals:
                    totals[k] += getattr(r, k)
    refresh_stats()
    dt = time.perf_counter() - t0
    print(f"backfill {days + 1} días x {len(STORES)} tiendas en {dt:.1f}s ({skipped} ya cargados): {totals}")


def run_once(day: date | None = None) -> int:
    """Scraping -> ETL -> estadísticas -> alertas, sin cola.

    Es el mismo trabajo que `tasks.scrape_all`, para entornos sin worker
    permanente (la demo gratuita lo ejecuta desde GitHub Actions cada 6 h).
    Cada tienda va en su propia transacción: si una falla, las demás se
    guardan igual. Devuelve el número de tiendas que fallaron.
    """
    from .alerts import evaluate_alerts

    day = day or date.today()
    failed = 0
    for slug in STORES:
        try:
            listings = get_source(slug).fetch(day)
            with SessionLocal.begin() as session:
                r = process_snapshot(session, store_snapshot(session, slug, day, listings))
            print(f"{slug}: {r.items} fichas, {r.new_products} productos nuevos")
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue con la siguiente tienda
            failed += 1
            print(f"{slug}: ERROR {exc!r}", file=sys.stderr)
    refresh_stats()
    with SessionLocal.begin() as session:
        print("alertas enviadas:", evaluate_alerts(session))
    return failed


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser(prog="radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    b = sub.add_parser("backfill")
    b.add_argument("--days", type=int, default=120)
    sub.add_parser("scrape")
    sub.add_parser("run")
    sub.add_parser("alerts")
    args = ap.parse_args()

    if args.cmd == "init":
        init_db()
        print("ok")
    elif args.cmd == "backfill":
        init_db()
        backfill(args.days)
    elif args.cmd == "scrape":
        from .tasks import scrape_all

        print("encolado:", scrape_all.delay().id)
    elif args.cmd == "run":
        init_db()
        sys.exit(1 if run_once() else 0)
    elif args.cmd == "alerts":
        from .alerts import evaluate_alerts

        refresh_stats()
        with SessionLocal.begin() as session:
            print("alertas enviadas:", evaluate_alerts(session))


if __name__ == "__main__":
    main()
