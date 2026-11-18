"""Adaptador genérico para tiendas sobre VTEX (catalog_system).

Varias cadenas latinoamericanas exponen `/api/catalog_system/pub/products/search`.
En noviembre de 2026 los endpoints públicos de las cadenas chilenas probadas
respondían 403/404 a clientes automáticos, por eso la demo usa la fuente
simulada. Este adaptador queda listo para una tienda cuyo endpoint se haya
verificado y cuyos términos permitan la consulta: se configura con
`VTEX_BASE_URL_<TIENDA>` (ej. `VTEX_BASE_URL_UNIMARC=https://www.unimarc.cl`).

Antes de activarlo contra un sitio real: revisar robots.txt y los términos de
uso, y mantener un rate limit bajo (ver `radar.http.PoliteClient`).
"""

from __future__ import annotations

import os
from datetime import date

from ..http import PoliteClient
from .base import RawListing, Source

DEFAULT_QUERIES = ["aceite", "arroz", "leche", "fideos", "azucar", "cafe", "detergente", "papel higienico"]


def parse_vtex_products(items: list[dict]) -> list[RawListing]:
    out: list[RawListing] = []
    for prod in items:
        for sku in prod.get("items", []):
            for seller in sku.get("sellers", [])[:1]:
                offer = seller.get("commertialOffer", {})
                price = offer.get("Price")
                if not price:
                    continue
                list_price = offer.get("ListPrice")
                out.append(
                    RawListing(
                        sku=str(sku.get("itemId")),
                        name=sku.get("nameComplete") or prod.get("productName", ""),
                        price=int(round(price)),
                        list_price=int(round(list_price)) if list_price and list_price > price else None,
                        brand=prod.get("brand"),
                        url=prod.get("link"),
                        available=offer.get("AvailableQuantity", 0) > 0,
                    )
                )
    return out


class VtexSource(Source):
    PAGE = 50

    def __init__(self, store_slug: str, client: PoliteClient | None = None, queries: list[str] | None = None):
        self.store_slug = store_slug
        env = "VTEX_BASE_URL_" + store_slug.upper().replace("-", "_")
        self.base_url = os.environ[env].rstrip("/")
        self.client = client or PoliteClient()
        self.queries = queries or DEFAULT_QUERIES

    def fetch(self, day: date) -> list[RawListing]:
        seen: dict[str, RawListing] = {}
        for q in self.queries:
            for start in range(0, 200, self.PAGE):
                items = self.client.get_json(
                    f"{self.base_url}/api/catalog_system/pub/products/search",
                    params={"ft": q, "_from": start, "_to": start + self.PAGE - 1},
                )
                if not items:
                    break
                for listing in parse_vtex_products(items):
                    seen[listing.sku] = listing
        return list(seen.values())
