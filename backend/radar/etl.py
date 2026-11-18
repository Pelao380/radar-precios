"""Pipeline ELT: snapshot crudo -> fichas normalizadas -> producto canónico -> historial.

Se separa en dos pasos idempotentes para que la cola pueda reintentar cada
uno por su cuenta:
  1. `store_snapshot`: guarda la respuesta cruda (bronze). Barato y casi
     nunca falla, así que un scraping exitoso nunca se pierde.
  2. `process_snapshot`: normaliza, deduplica y registra precios. Se puede
     re-ejecutar sobre el mismo snapshot sin duplicar datos (upserts).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import Listing, PriceObservation, Product, RawSnapshot, Store
from .embeddings import Embedder, get_embedder
from .matching import Candidate, decide
from .normalize import normalize
from .sources.base import RawListing
from .sources.catalog import STORES

log = logging.getLogger(__name__)


@dataclass
class EtlResult:
    snapshot_id: int
    items: int = 0
    new_listings: int = 0
    new_products: int = 0
    matched_existing: int = 0
    observations: int = 0


def ensure_stores(session: Session) -> dict[str, int]:
    existing = {s.slug: s.id for s in session.scalars(select(Store))}
    for slug, name in STORES.items():
        if slug not in existing:
            st = Store(slug=slug, name=name)
            session.add(st)
            session.flush()
            existing[slug] = st.id
    return existing


def store_snapshot(session: Session, store_slug: str, day: date, listings: list[RawListing]) -> int:
    store_ids = ensure_stores(session)
    snap = RawSnapshot(
        store_id=store_ids[store_slug],
        observed_on=day,
        item_count=len(listings),
        payload=[item.to_dict() for item in listings],
    )
    session.add(snap)
    session.flush()
    return snap.id


def _candidates(session: Session, norm, embedding, k: int = 5) -> list[Candidate]:
    """Vecinos más cercanos por coseno (índice HNSW) dentro del mismo bloque de tamaño."""
    stmt = (
        select(Product)
        .where(Product.size_unit.is_(norm.size_unit) if norm.size_unit is None else Product.size_unit == norm.size_unit)
        .where(Product.size_qty.is_(None) if norm.size_qty is None else Product.size_qty == norm.size_qty)
        .order_by(Product.embedding.cosine_distance(embedding))
        .limit(k)
    )
    return [
        Candidate(p.id, p.brand, p.size_qty, p.size_unit, list(p.embedding), p.clean_name)
        for p in session.scalars(stmt)
    ]


def _pretty_name(raw: str) -> str:
    return raw if not raw.isupper() else raw.title()


def process_snapshot(session: Session, snapshot_id: int, embedder: Embedder | None = None) -> EtlResult:
    embedder = embedder or get_embedder()
    snap = session.get(RawSnapshot, snapshot_id)
    if snap is None:
        raise ValueError(f"snapshot {snapshot_id} no existe")
    result = EtlResult(snapshot_id=snapshot_id, items=snap.item_count)

    existing = {li.sku: li for li in session.scalars(select(Listing).where(Listing.store_id == snap.store_id))}
    new_items = [RawListing(**d) for d in snap.payload if d["sku"] not in existing]
    norms = [normalize(it.name, it.brand) for it in new_items]
    embeddings = embedder.embed([n.match_text for n in norms]) if norms else []

    for item, norm, emb in zip(new_items, norms, embeddings):
        decision = decide(norm, emb, _candidates(session, norm, emb))
        if decision.product_id is None:
            product = Product(
                canonical_name=_pretty_name(item.name),
                clean_name=norm.clean_name,
                brand=norm.brand,
                size_qty=norm.size_qty,
                size_unit=norm.size_unit,
                size_label=norm.size_label,
                embedding=emb,
            )
            session.add(product)
            session.flush()
            product_id = product.id
            result.new_products += 1
        else:
            product_id = decision.product_id
            result.matched_existing += 1
        listing = Listing(
            store_id=snap.store_id,
            sku=item.sku,
            raw_name=item.name,
            url=item.url,
            product_id=product_id,
            match_score=decision.score or None,
            first_seen=snap.observed_on,
            last_seen=snap.observed_on,
        )
        session.add(listing)
        session.flush()
        existing[item.sku] = listing
        result.new_listings += 1

    rows = []
    seen_ids = []
    for d in snap.payload:
        listing = existing[d["sku"]]
        seen_ids.append(listing.id)
        rows.append(
            {
                "listing_id": listing.id,
                "observed_on": snap.observed_on,
                "price": d["price"],
                "list_price": d.get("list_price"),
            }
        )
    if rows:
        stmt = insert(PriceObservation).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["listing_id", "observed_on"],
            set_={"price": stmt.excluded.price, "list_price": stmt.excluded.list_price},
        )
        session.execute(stmt)
        # un solo UPDATE por snapshot (antes: uno por ficha, ~40 viajes de red a una base remota)
        session.execute(
            update(Listing)
            .where(Listing.id.in_(seen_ids), Listing.last_seen < snap.observed_on)
            .values(last_seen=snap.observed_on)
            .execution_options(synchronize_session=False)
        )
    result.observations = len(rows)
    snap.processed = True
    log.info("ETL snapshot=%s %s", snapshot_id, result)
    return result
