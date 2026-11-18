"""Deduplicación de productos entre tiendas.

Problema: Lider llama "Aceite Vegetal Belmont 1 L" a lo que Unimarc llama
"ACEITE BELMONT VEGETAL BOTELLA 1 LITRO". Necesitamos un id canónico de producto
para comparar precios entre tiendas.

Estrategia (ver README, sección "Deduplicación"):
1. *Blocking* por tamaño y unidad normalizados: un 1 L nunca se fusiona con 900 ml.
2. Si ambas fichas tienen marca y difieren, no son el mismo producto.
3. Similitud coseno entre embeddings de `marca + nombre limpio` >= umbral.

El embedder por defecto es un *hashing embedder* de n-gramas de caracteres:
determinista, sin dependencias y sin costo, y sirve para tests y CI. En
producción se puede cambiar por Voyage (`EMBEDDINGS_PROVIDER=voyage`) sin tocar
el resto, porque ambos producen vectores L2-normalizados de `EMBED_DIM` dimensiones.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .normalize import NormalizedProduct

EMBED_DIM = 512
DEFAULT_THRESHOLD = 0.75


def _features(text: str) -> Iterable[tuple[str, float]]:
    words = text.split()
    for w in words:
        yield f"w:{w}", 1.0
        padded = f"#{w}#"
        for i in range(len(padded) - 2):
            yield f"c:{padded[i : i + 3]}", 0.5
    for a, b in zip(words, words[1:]):
        yield f"b:{a}_{b}", 0.5


def hashing_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    vec = [0.0] * dim
    for feat, weight in _features(text):
        h = hashlib.blake2b(feat.encode(), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


@dataclass(frozen=True)
class Candidate:
    product_id: int
    brand: str | None
    size_qty: float | None
    size_unit: str | None
    embedding: Sequence[float]
    clean_name: str = ""


@dataclass(frozen=True)
class MatchDecision:
    product_id: int | None
    score: float
    reason: str


def same_block(p: NormalizedProduct, c: Candidate) -> bool:
    if p.size_unit != c.size_unit:
        return False
    if p.size_qty is None or c.size_qty is None:
        return p.size_qty is None and c.size_qty is None
    return abs(p.size_qty - c.size_qty) < 1e-6


def brands_compatible(a: str | None, b: str | None) -> bool:
    return a is None or b is None or a == b


# Atributos mutuamente excluyentes. Un embedding ve "agua sin gas" y "agua con
# gas" como casi idénticos (difieren en una palabra), pero para comparar precios
# son productos distintos. Es una restricción dura que se aplica antes del coseno.
CONFLICT_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"sin", "con"}),
    frozenset({"entera", "descremada", "semidescremada", "descrem", "semidesc"}),
    frozenset({"original", "zero", "light"}),
    frozenset({"blanco", "integral"}),
    frozenset({"vegetal", "girasol", "oliva"}),
)
# abreviaturas que pertenecen al mismo valor
_SAME_VALUE = {"descrem": "descremada", "semidesc": "semidescremada"}


def attributes_conflict(a: str, b: str) -> bool:
    ta = {_SAME_VALUE.get(t, t) for t in a.split()}
    tb = {_SAME_VALUE.get(t, t) for t in b.split()}
    for group in CONFLICT_GROUPS:
        ga, gb = ta & group, tb & group
        if ga and gb and ga != gb:
            return True
    return False


def decide(
    product: NormalizedProduct,
    embedding: Sequence[float],
    candidates: Iterable[Candidate],
    threshold: float = DEFAULT_THRESHOLD,
) -> MatchDecision:
    """Elige el producto canónico al que pertenece la ficha, o None si es nuevo."""
    best: MatchDecision = MatchDecision(None, 0.0, "sin candidatos")
    for c in candidates:
        if not same_block(product, c):
            continue
        if not brands_compatible(product.brand, c.brand):
            continue
        if attributes_conflict(product.clean_name, c.clean_name):
            continue
        score = cosine(embedding, c.embedding)
        if score > best.score:
            best = MatchDecision(c.product_id, score, "embedding")
    if best.product_id is not None and best.score >= threshold:
        return best
    return MatchDecision(None, best.score, f"bajo umbral ({best.score:.2f})")


def cluster(
    items: Sequence[NormalizedProduct],
    embed=hashing_embed,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[int]:
    """Agrupa una lista completa en memoria (lo usa la evaluación offline).

    Devuelve, para cada ítem, el índice de su cluster. Es el mismo algoritmo
    incremental que corre el ETL contra la base de datos.
    """
    reps: list[Candidate] = []
    labels: list[int] = []
    for p in items:
        emb = embed(p.match_text)
        d = decide(p, emb, reps, threshold)
        if d.product_id is None:
            cid = len(reps)
            reps.append(Candidate(cid, p.brand, p.size_qty, p.size_unit, emb, p.clean_name))
            labels.append(cid)
        else:
            labels.append(d.product_id)
    return labels
