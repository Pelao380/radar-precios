from __future__ import annotations

from ..config import settings
from .base import RawListing, Source
from .catalog import STORES
from .simulated import SimulatedSource


def get_source(store_slug: str, mode: str | None = None) -> Source:
    mode = mode or settings.source_mode
    if mode == "vtex":
        from .vtex import VtexSource

        return VtexSource(store_slug)
    return SimulatedSource(store_slug)


__all__ = ["RawListing", "Source", "STORES", "get_source"]
