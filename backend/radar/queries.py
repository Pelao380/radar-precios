"""Consultas de lectura compartidas por la API, la búsqueda y las alertas."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from .stats import PricePoint, compute

PRODUCT_LIST_SQL = """
SELECT p.id, p.canonical_name, p.brand, p.size_label,
       ps.best_price, ps.min_90d, ps.max_90d, ps.median_30d, ps.min_90d_before_today,
       (SELECT cp.store_name FROM current_prices cp
         WHERE cp.product_id = p.id ORDER BY cp.price LIMIT 1) AS best_store,
       (SELECT COUNT(DISTINCT cp.store) FROM current_prices cp WHERE cp.product_id = p.id) AS n_stores
FROM products p
JOIN product_stats ps ON ps.product_id = p.id
"""


def _row_to_summary(r) -> dict:
    median = float(r.median_30d) if r.median_30d is not None else None
    drop = round((median - r.best_price) / median * 100, 1) if median else 0.0
    return {
        "id": r.id,
        "name": r.canonical_name,
        "brand": r.brand,
        "size": r.size_label,
        "best_price": r.best_price,
        "best_store": r.best_store,
        "n_stores": r.n_stores,
        "min_90d": r.min_90d,
        "max_90d": r.max_90d,
        "median_30d": median,
        "drop_pct": drop,
        "is_lowest_90d": r.min_90d_before_today is not None and r.best_price < r.min_90d_before_today,
    }


def list_products(session: Session, q: str | None = None, limit: int = 50, ids: list[int] | None = None) -> list[dict]:
    sql = PRODUCT_LIST_SQL + " WHERE TRUE"
    params: dict = {"limit": limit}
    if q:
        sql += " AND (p.canonical_name ILIKE :q OR p.clean_name ILIKE :q OR p.brand ILIKE :q)"
        params["q"] = f"%{q}%"
    if ids is not None:
        sql += " AND p.id = ANY(:ids)"
        params["ids"] = ids
    sql += " ORDER BY p.canonical_name LIMIT :limit"
    return [_row_to_summary(r) for r in session.execute(text(sql), params)]


def deals(session: Session, limit: int = 12, min_drop_pct: float = 10.0) -> list[dict]:
    rows = [_row_to_summary(r) for r in session.execute(text(PRODUCT_LIST_SQL))]
    hits = [r for r in rows if r["is_lowest_90d"] or r["drop_pct"] >= min_drop_pct]
    hits.sort(key=lambda r: (r["drop_pct"], r["is_lowest_90d"]), reverse=True)
    return hits[:limit]


def product_history(session: Session, product_id: int, days: int = 90) -> dict:
    """Serie diaria por tienda + estadísticas sobre el mejor precio diario."""
    rows = session.execute(
        text(
            """
            SELECT s.slug, s.name, o.observed_on, o.price, o.list_price
            FROM price_observations o
            JOIN listings l ON l.id = o.listing_id
            JOIN stores s ON s.id = l.store_id
            WHERE l.product_id = :pid
              AND o.observed_on > (SELECT MAX(observed_on) FROM price_observations) - :days
            ORDER BY o.observed_on
            """
        ),
        {"pid": product_id, "days": days},
    ).all()
    by_day: dict[date, dict] = {}
    best: dict[date, int] = {}
    stores: dict[str, str] = {}
    for slug, name, day, price, _ in rows:
        stores[slug] = name
        by_day.setdefault(day, {"day": day.isoformat()})[slug] = price
        best[day] = min(best.get(day, price), price)
    stats = compute([PricePoint(d, p) for d, p in sorted(best.items())])
    return {
        "stores": [{"slug": k, "name": v} for k, v in stores.items()],
        "series": [by_day[d] | {"best": best[d]} for d in sorted(by_day)],
        "stats": stats.__dict__ if stats else None,
    }


def product_detail(session: Session, product_id: int) -> dict | None:
    p = session.execute(
        text("SELECT id, canonical_name, brand, size_label, size_qty, size_unit FROM products WHERE id = :id"),
        {"id": product_id},
    ).one_or_none()
    if p is None:
        return None
    offers = (
        session.execute(
            text(
                """
            SELECT cp.store, cp.store_name, cp.price, cp.list_price, cp.observed_on, cp.url, l.raw_name
            FROM current_prices cp JOIN listings l ON l.id = cp.listing_id
            WHERE cp.product_id = :id ORDER BY cp.price
            """
            ),
            {"id": product_id},
        )
        .mappings()
        .all()
    )
    return {
        "id": p.id,
        "name": p.canonical_name,
        "brand": p.brand,
        "size": p.size_label,
        "offers": [dict(o) | {"observed_on": o["observed_on"].isoformat()} for o in offers],
        **product_history(session, product_id),
    }


def overview(session: Session) -> dict:
    r = session.execute(
        text(
            """
            SELECT (SELECT COUNT(*) FROM products) AS products,
                   (SELECT COUNT(*) FROM listings) AS listings,
                   (SELECT COUNT(*) FROM price_observations) AS observations,
                   (SELECT MIN(observed_on) FROM price_observations) AS since,
                   (SELECT MAX(observed_on) FROM price_observations) AS last_day,
                   (SELECT COUNT(*) FROM stores) AS stores
            """
        )
    ).one()
    return {
        "products": r.products,
        "listings": r.listings,
        "observations": r.observations,
        "stores": r.stores,
        "since": r.since.isoformat() if r.since else None,
        "last_day": r.last_day.isoformat() if r.last_day else None,
        "dedup_ratio": round(r.listings / r.products, 2) if r.products else None,
    }


def best_daily_series(session: Session, product_id: int, days: int = 120) -> list[PricePoint]:
    rows = session.execute(
        text(
            """
            SELECT o.observed_on, MIN(o.price)
            FROM price_observations o JOIN listings l ON l.id = o.listing_id
            WHERE l.product_id = :pid AND o.observed_on > (SELECT MAX(observed_on) FROM price_observations) - :days
            GROUP BY o.observed_on ORDER BY o.observed_on
            """
        ),
        {"pid": product_id, "days": days},
    ).all()
    return [PricePoint(d, p) for d, p in rows]
