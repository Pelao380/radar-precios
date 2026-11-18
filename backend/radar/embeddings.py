"""Proveedores de embeddings intercambiables.

- `hashing`: n-gramas de caracteres con hashing, local y determinista. Es el default.
- `voyage`: API de Voyage AI (`VOYAGE_API_KEY`), proveedor recomendado por
  Anthropic para embeddings. Se pide `output_dimension=EMBED_DIM` para que la
  columna pgvector no cambie de tamaño al cambiar de proveedor.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Protocol

from .matching import EMBED_DIM, hashing_embed


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]: ...


class HashingEmbedder:
    name = "hashing"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [hashing_embed(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return hashing_embed(text)


class VoyageEmbedder:
    name = "voyage"
    URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(self, model: str = "voyage-3.5-lite"):
        self.model = model
        self.api_key = os.environ["VOYAGE_API_KEY"]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import httpx

        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            resp = httpx.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "input": list(texts[i : i + 128]),
                    "model": self.model,
                    "output_dimension": EMBED_DIM,
                    "input_type": "document",
                },
                timeout=30,
            )
            resp.raise_for_status()
            out.extend(d["embedding"] for d in resp.json()["data"])
        return out

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def get_embedder(provider: str | None = None) -> Embedder:
    provider = provider or os.environ.get("EMBEDDINGS_PROVIDER", "hashing")
    if provider == "voyage":
        return VoyageEmbedder()
    return HashingEmbedder()
