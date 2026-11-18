from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class RawListing:
    """Una ficha de producto tal como la entrega la tienda (capa bronze)."""

    sku: str
    name: str
    price: int
    list_price: int | None = None
    brand: str | None = None
    url: str | None = None
    available: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class Source(ABC):
    """Adaptador de una tienda. Cada tienda nueva = una subclase."""

    store_slug: str

    @abstractmethod
    def fetch(self, day: date) -> list[RawListing]:
        """Devuelve el catálogo observado en `day`."""
