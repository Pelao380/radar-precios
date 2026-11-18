"""Búsqueda en lenguaje natural.

pregunta --(intent: LLM o reglas)--> filtros --(embedding + pgvector)--> productos
         --(SQL)--> precios reales --(plantilla)--> respuesta

La respuesta final se arma con una plantilla a partir de filas de la base de
datos, no con el LLM. Así cada número que ve el usuario es trazable a una
observación.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from .embeddings import get_embedder
from .intent import SearchIntent, parse
from .normalize import normalize

SEMANTIC_SQL = """
SELECT p.id, 1 - (p.embedding <=> CAST(:emb AS vector)) AS similarity
FROM products p
WHERE (CAST(:unit AS text) IS NULL OR p.size_unit = :unit)
  AND (CAST(:qty AS float) IS NULL OR p.size_qty = :qty)
ORDER BY p.embedding <=> CAST(:emb AS vector)
LIMIT 30
"""

OFFERS_SQL = """
SELECT p.id AS product_id, p.canonical_name, p.size_label, s.slug AS store, s.name AS store_name,
       MIN(o.price) AS min_price,
       MAX(o.price) AS max_price,
       (ARRAY_AGG(o.price ORDER BY o.observed_on DESC))[1] AS last_price,
       MAX(o.observed_on) AS last_seen
FROM price_observations o
JOIN listings l ON l.id = o.listing_id
JOIN products p ON p.id = l.product_id
JOIN stores s ON s.id = l.store_id
WHERE p.id = ANY(:ids)
  AND o.observed_on > (SELECT MAX(observed_on) FROM price_observations) - :days
  AND (CAST(:store AS text) IS NULL OR s.slug = :store)
GROUP BY p.id, p.canonical_name, p.size_label, s.slug, s.name
"""


def _fmt_clp(n: int) -> str:
    return "$" + f"{n:,}".replace(",", ".")


def search(session: Session, query: str, intent: SearchIntent | None = None, min_similarity: float = 0.35) -> dict:
    intent = intent or parse(query)
    probe = normalize(intent.product)
    emb = get_embedder().embed_one(probe.match_text or intent.product)
    hits = session.execute(
        text(SEMANTIC_SQL),
        {"emb": str(emb), "unit": intent.size_unit, "qty": intent.size_qty},
    ).all()
    ids = [h.id for h in hits if h.similarity >= min_similarity]
    sim = {h.id: float(h.similarity) for h in hits}

    offers = []
    if ids:
        rows = (
            session.execute(text(OFFERS_SQL), {"ids": ids, "days": intent.period_days, "store": intent.store})
            .mappings()
            .all()
        )
        offers = [
            dict(r) | {"last_seen": r["last_seen"].isoformat(), "similarity": round(sim[r["product_id"]], 3)}
            for r in rows
        ]

    if intent.max_price is not None:
        offers = [o for o in offers if o["last_price"] <= intent.max_price]

    if intent.sort == "biggest_drop":
        # mayor caída del precio vigente respecto al máximo del periodo
        for o in offers:
            o["drop_pct"] = round((o["max_price"] - o["last_price"]) / o["max_price"] * 100, 1)
        offers.sort(key=lambda o: (-o["drop_pct"], o["last_price"]))
    else:
        offers.sort(key=lambda o: (o["last_price"], -o["similarity"]))

    return {"query": query, "intent": intent.to_dict(), "answer": _answer(intent, offers), "results": offers[:20]}


def _answer(intent: SearchIntent, offers: list[dict]) -> str:
    period = {1: "hoy", 7: "esta semana", 30: "este mes"}.get(
        intent.period_days, f"en los últimos {intent.period_days} días"
    )
    if not offers:
        return f"No encontré precios para «{intent.product}» {period}."
    best = offers[0]
    if intent.sort == "biggest_drop":
        return (
            f"La mayor rebaja {period}: {best['canonical_name']} ({best['size_label']}) en "
            f"{best['store_name']}, de {_fmt_clp(best['max_price'])} a {_fmt_clp(best['last_price'])} "
            f"(-{best['drop_pct']:.0f}%)."
        )
    text_ = (
        f"El más barato {period} es {best['canonical_name']} ({best['size_label']}) en "
        f"{best['store_name']} a {_fmt_clp(best['last_price'])}"
    )
    if best["min_price"] < best["last_price"]:
        text_ += f"; en el periodo llegó a {_fmt_clp(best['min_price'])}"
    others = [o for o in offers[1:4] if o["product_id"] == best["product_id"]]
    if others:
        text_ += ". En otras tiendas: " + ", ".join(f"{o['store_name']} {_fmt_clp(o['last_price'])}" for o in others)
    return text_ + "."
