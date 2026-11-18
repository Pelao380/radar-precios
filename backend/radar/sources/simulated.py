"""Fuente simulada determinista.

Genera precios con una caminata aleatoria suave + promociones periódicas,
sembrada por (tienda, sku, día). El mismo día siempre produce los mismos
precios, por lo que la demo y los tests son reproducibles.
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date

from .base import RawListing, Source
from .catalog import CATALOG, STORE_PRICE_FACTOR, STORES, store_name

EPOCH = date(2025, 1, 1)


def _rng(*parts: object) -> random.Random:
    seed = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def _round_clp(x: float) -> int:
    """Precios chilenos terminan en 90 o 0."""
    return max(90, int(round(x / 100.0)) * 100 - 10)


def simulated_price(store: str, key: str, base_price: int, day: date) -> tuple[int, int | None]:
    t = (day - EPOCH).days
    prod_rng = _rng(store, key)
    phase = prod_rng.uniform(0, 2 * math.pi)
    promo_every = prod_rng.choice([21, 28, 35, 45])
    promo_len = prod_rng.choice([3, 5, 7])
    promo_depth = prod_rng.uniform(0.12, 0.30)
    drift = prod_rng.uniform(0.0, 0.00025)  # inflación diaria

    level = base_price * STORE_PRICE_FACTOR[store] * (1 + drift) ** t
    seasonal = 1 + 0.03 * math.sin(2 * math.pi * t / 60 + phase)
    noise = 1 + _rng(store, key, day.isoformat()).uniform(-0.015, 0.015)
    regular = _round_clp(level * seasonal * noise)

    offset = int(prod_rng.uniform(0, promo_every))
    if (t + offset) % promo_every < promo_len:
        return _round_clp(regular * (1 - promo_depth)), regular
    return regular, None


class SimulatedSource(Source):
    def __init__(self, store_slug: str):
        if store_slug not in STORES:
            raise ValueError(f"tienda desconocida: {store_slug}")
        self.store_slug = store_slug

    def fetch(self, day: date) -> list[RawListing]:
        out: list[RawListing] = []
        for p in CATALOG:
            rng = _rng(self.store_slug, p.key, "stock", day.isoformat())
            if rng.random() < 0.03:  # 3% de quiebre de stock
                continue
            price, list_price = simulated_price(self.store_slug, p.key, p.base_price, day)
            sku = hashlib.md5(f"{self.store_slug}:{p.key}".encode()).hexdigest()[:10]
            out.append(
                RawListing(
                    sku=sku,
                    name=store_name(p, self.store_slug),
                    price=price,
                    list_price=list_price,
                    # solo Jumbo expone la marca como campo separado
                    brand=p.brand if self.store_slug == "jumbo" else None,
                    url=f"https://example.invalid/{self.store_slug}/{sku}",
                )
            )
        return out


def ground_truth() -> list[tuple[str, str, str]]:
    """(tienda, nombre crudo, clave real) para evaluar la deduplicación."""
    return [(s, store_name(p, s), p.key) for p in CATALOG for s in STORES]
