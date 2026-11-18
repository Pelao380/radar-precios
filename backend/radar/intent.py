"""Convierte una pregunta en lenguaje natural en una consulta estructurada.

"¿dónde está más barato el aceite de 1 L esta semana?"
  -> SearchIntent(product="aceite", size_qty=1000, size_unit="ml",
                  period_days=7, sort="cheapest")

Decisión de diseño: el LLM **solo traduce** la pregunta a filtros. Los precios
y la respuesta salen de SQL, así que el modelo no puede inventar un precio.
Si no hay `ANTHROPIC_API_KEY`, o la llamada falla, se usa el parser de reglas,
así que la búsqueda nunca se cae por la IA.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import Literal

from .normalize import _basic_clean, parse_size
from .sources.catalog import STORES

log = logging.getLogger(__name__)

Sort = Literal["cheapest", "biggest_drop"]


@dataclass
class SearchIntent:
    product: str
    size_qty: float | None = None
    size_unit: str | None = None
    store: str | None = None
    max_price: int | None = None
    period_days: int = 7
    sort: Sort = "cheapest"
    parser: str = "rules"

    def to_dict(self) -> dict:
        return asdict(self)


_QUESTION_WORDS = frozenset(
    """donde esta mas barato barata baratos baratas el la los las de del que cual
    cuales precio precios hoy semana mes este esta en a un una me conviene comprar
    oferta ofertas descuento descuentos bajo menos hay quiero busco encuentro
    mejor tienda supermercado super por ultimos ultimas dias bajaron bajo
    caida cayo y o con para""".split()
)
_STORE_ALIASES = {
    "lider": "lider",
    "walmart": "lider",
    "jumbo": "jumbo",
    "unimarc": "unimarc",
    "santa isabel": "santa-isabel",
    "santaisabel": "santa-isabel",
}


def parse_rules(query: str) -> SearchIntent:
    text = _basic_clean(query)
    size_qty, size_unit, _ = parse_size(text)

    store = None
    for alias, slug in _STORE_ALIASES.items():
        if f" {alias} " in f" {text} ":
            store = slug
            text = f" {text} ".replace(f" {alias} ", " ").strip()

    max_price = None
    m = re.search(r"(?:menos de|bajo|hasta|max(?:imo)?)\s*\$?\s*(\d[\d.]*)", text)
    if m:
        max_price = int(m.group(1).replace(".", ""))
        text = text.replace(m.group(0), " ")

    period = 7
    if re.search(r"\bhoy\b", text):
        period = 1
    elif re.search(r"\bmes\b|30 dias", text):
        period = 30
    elif m2 := re.search(r"(\d+)\s*dias", text):
        period = int(m2.group(1))

    sort: Sort = (
        "biggest_drop" if re.search(r"\b(oferta|ofertas|bajaron|bajo|caida|cayo|descuento)", text) else "cheapest"
    )

    # el producto es lo que queda tras quitar tamaño, números y palabras de pregunta
    rest = re.sub(r"\d+(?:[.,]\d+)?\s*(ml|l|g|kg|un)\b", " ", text)
    words = [w for w in rest.split() if w not in _QUESTION_WORDS and not w.isdigit() and w not in ("dias",)]
    return SearchIntent(
        product=" ".join(words),
        size_qty=size_qty,
        size_unit=size_unit,
        store=store,
        max_price=max_price,
        period_days=period,
        sort=sort,
    )


SYSTEM_PROMPT = f"""Traduces preguntas sobre precios de supermercados chilenos a filtros de búsqueda.
Tiendas válidas (usa el slug): {", ".join(STORES)}.
- product: el producto en palabras simples en español, sin marca salvo que la pidan, sin tamaño (ej. "aceite", "leche descremada", "arroz grado 1").
- size_qty/size_unit: tamaño normalizado a ml, g o un (1 L -> 1000 ml, 1 kg -> 1000 g). null si no lo mencionan.
- period_days: 1 para "hoy", 7 para "esta semana" o si no lo dicen, 30 para "este mes".
- sort: "biggest_drop" si preguntan por ofertas, rebajas o lo que más bajó; si no, "cheapest".
- max_price: tope en pesos chilenos si lo mencionan, si no null."""


def parse_llm(query: str) -> SearchIntent:
    import anthropic
    from pydantic import BaseModel

    class LLMIntent(BaseModel):
        product: str
        size_qty: float | None
        size_unit: Literal["ml", "g", "un"] | None
        store: Literal["lider", "jumbo", "unimarc", "santa-isabel"] | None
        max_price: int | None
        period_days: int
        sort: Literal["cheapest", "biggest_drop"]

    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
        max_tokens=1024,
        # Esta tarea es una traducción simple: con esfuerzo bajo la latencia es menor.
        output_config={"effort": "low"},
        # Si el clasificador de seguridad rechaza, el servidor reintenta en otro modelo.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
        output_format=LLMIntent,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ValueError(f"sin intención estructurada (stop_reason={response.stop_reason})")
    return SearchIntent(**response.parsed_output.model_dump(), parser="llm")


def parse(query: str) -> SearchIntent:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return parse_llm(query)
        except Exception as exc:  # la búsqueda no debe caerse por la IA
            log.warning("parse_llm falló, uso reglas: %s", exc)
    return parse_rules(query)
