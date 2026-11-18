"""Comandos de mantenimiento.

python -m radar.cli init                 # crea extensión, tablas y vistas
python -m radar.cli backfill --days 120  # historial simulado (síncrono, sin cola)
python -m radar.cli scrape               # encola un scraping de todas las tiendas
python -m radar.cli alerts               # evalúa alertas ahora
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta

from sqlalchemy import text

from .db import SessionLocal, init_db, refresh_stats
from .etl import process_snapshot, store_snapshot
from .sources import STORES, get_source


def backfill(days: int, end: date | None = None) -> None:
    """Carga `days` días de historial ejecutando el mismo ETL que la cola."""
    end = end or date.today()
    t0 = time.perf_counter()
    totals = {"observations": 0, "new_products": 0, "new_listings": 0}
    for i in range(days, -1, -1):
        day = end - timedelta(days=i)
        with SessionLocal.begin() as session:
            for slug in STORES:
                snap_id = store_snapshot(session, slug, day, get_source(slug, "simulated").fetch(day))
                r = process_snapshot(session, snap_id)
                for k in totals:
                    totals[k] += getattr(r, k)
    refresh_stats()
    dt = time.perf_counter() - t0
    print(f"backfill {days + 1} días x {len(STORES)} tiendas en {dt:.1f}s: {totals}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser(prog="radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    b = sub.add_parser("backfill")
    b.add_argument("--days", type=int, default=120)
    b.add_argument("--force", action="store_true", help="cargar aunque ya existan datos")
    sub.add_parser("scrape")
    sub.add_parser("alerts")
    args = ap.parse_args()

    if args.cmd == "init":
        init_db()
        print("ok")
    elif args.cmd == "backfill":
        init_db()
        with SessionLocal() as session:
            has_data = session.execute(text("SELECT EXISTS (SELECT 1 FROM price_observations)")).scalar()
        if has_data and not args.force:
            print("ya hay datos; backfill omitido (usa --force para recargar)")
        else:
            backfill(args.days)
    elif args.cmd == "scrape":
        from .tasks import scrape_all

        print("encolado:", scrape_all.delay().id)
    elif args.cmd == "alerts":
        from .alerts import evaluate_alerts

        refresh_stats()
        with SessionLocal.begin() as session:
            print("alertas enviadas:", evaluate_alerts(session))


if __name__ == "__main__":
    main()
