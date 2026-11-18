"""Normalización de nombres de productos de supermercado.

Funciones puras (sin I/O) para que sean fáciles de testear. Convierte un nombre
crudo como "ACEITE VEGETAL BELMONT 1 LITRO" en una estructura comparable:

    NormalizedProduct(clean_name="aceite vegetal", brand="belmont",
                      size_qty=1000.0, size_unit="ml", pack=1)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Marcas conocidas del catálogo. En producción vendría de una tabla; para la
# demo basta una lista. Se comparan sin tildes y en minúscula.
KNOWN_BRANDS: tuple[str, ...] = (
    "belmont",
    "chef",
    "natura",
    "miraflores",
    "soprole",
    "colun",
    "loncoleche",
    "nestle",
    "carozzi",
    "lucchetti",
    "tucapel",
    "banquete",
    "iansa",
    "nescafe",
    "cachantun",
    "coca cola",
    "ideal",
    "castano",
    "lider",
    "jumbo",
    "cuisine & co",
    "unimarc",
    "great value",
    "omo",
    "ariel",
    "confort",
    "elite",
    "noble",
    "pf",
    "san jorge",
    "dos alamos",
    "selecta",
    "watts",
    "calo",
    "quaker",
    "costa",
)

# Sinónimos regionales y abreviaturas que las tiendas usan de forma distinta.
SYNONYMS: dict[str, str] = {
    "maravilla": "girasol",
    "descremada": "descremada",
    "semidescremada": "semidescremada",
    "lt": "l",
    "lts": "l",
    "litro": "l",
    "litros": "l",
    "grs": "g",
    "gr": "g",
    "gramos": "g",
    "kilo": "kg",
    "kilos": "kg",
    "cc": "ml",
    "unidades": "un",
    "unid": "un",
    "und": "un",
    "uds": "un",
    "papel higienico": "papel higienico",
}

STOPWORDS = frozenset(
    {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "en",
        "y",
        "para",
        "n",
        "nro",
        "botella",
        "bolsa",
        "caja",
        "pack",
        "paquete",
        "formato",
        "familiar",
        "marca",
        "x",
        "envase",
        "doypack",
        "tarro",
        "sachet",
    }
)

_UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "un": ("un", 1.0),
}

# "6 x 350 ml", "6x350ml"
_PACK_RE = re.compile(r"(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*(ml|l|g|kg|un)\b")
# "1 l", "900ml", "1,5 l", "500 g", "12 un"
_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ml|l|g|kg|un)\b")


@dataclass(frozen=True)
class NormalizedProduct:
    clean_name: str
    brand: str | None
    size_qty: float | None  # en unidad base (ml, g, un), total del pack
    size_unit: str | None  # "ml" | "g" | "un"
    pack: int = 1

    @property
    def size_label(self) -> str:
        if self.size_qty is None or self.size_unit is None:
            return ""
        qty, unit = self.size_qty, self.size_unit
        if unit == "ml" and qty >= 1000:
            return f"{_fmt(qty / 1000)} L"
        if unit == "g" and qty >= 1000:
            return f"{_fmt(qty / 1000)} kg"
        return f"{_fmt(qty)} {unit}"

    @property
    def match_text(self) -> str:
        """Texto que se embebe para deduplicar: marca + nombre limpio."""
        return " ".join(p for p in (self.brand, self.clean_name) if p)


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _basic_clean(raw: str) -> str:
    text = strip_accents(raw).lower()
    text = text.replace("&", " & ")
    # "S/Gas" -> "sin gas", "C/Gas" -> "con gas" (antes de borrar la barra)
    text = re.sub(r"(?<![a-z])s/", "sin ", text)
    text = re.sub(r"(?<![a-z])c/", "con ", text)
    text = re.sub(r"[^a-z0-9.,&x ]+", " ", text)
    # separa números pegados a unidades: "1lt" -> "1 lt"; "6x350ml" -> "6 x 350 ml"
    text = re.sub(r"(\d)([a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z])(\d)", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    # aplica sinónimos palabra por palabra
    words = [SYNONYMS.get(w, w) for w in text.split(" ")]
    return " ".join(words)


def parse_size(text: str) -> tuple[float | None, str | None, int]:
    """Extrae tamaño total en unidad base. `text` debe venir ya limpio."""
    m = _PACK_RE.search(text)
    if m:
        pack = int(m.group(1))
        qty = float(m.group(2).replace(",", "."))
        base_unit, factor = _UNIT_FACTORS[m.group(3)]
        return round(pack * qty * factor, 3), base_unit, pack
    m = _SIZE_RE.search(text)
    if m:
        qty = float(m.group(1).replace(",", "."))
        base_unit, factor = _UNIT_FACTORS[m.group(2)]
        return round(qty * factor, 3), base_unit, 1
    return None, None, 1


def find_brand(text: str, hint: str | None = None) -> str | None:
    if hint:
        h = _basic_clean(hint)
        if h:
            return h
    padded = f" {text} "
    # marcas más largas primero ("coca cola" antes que "coca")
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if f" {brand} " in padded:
            return brand
    return None


def normalize(raw_name: str, brand_hint: str | None = None) -> NormalizedProduct:
    text = _basic_clean(raw_name)
    size_qty, size_unit, pack = parse_size(text)
    brand = find_brand(text, brand_hint)

    # quita tamaño, marca y stopwords del nombre
    name = _PACK_RE.sub(" ", text)
    name = _SIZE_RE.sub(" ", name)
    if brand:
        name = f" {name} ".replace(f" {brand} ", " ")
    # los números sueltos se conservan: "grado 1" != "grado 2", "spaghetti 5"
    tokens = [t for t in name.split() if t not in STOPWORDS]
    # orden canónico: las tiendas reordenan palabras ("aceite vegetal" / "vegetal aceite")
    # pero el primer token suele ser la categoría, así que se conserva primero.
    if tokens:
        head, rest = tokens[0], sorted(set(tokens[1:]) - {tokens[0]})
        tokens = [head, *rest]
    return NormalizedProduct(
        clean_name=" ".join(tokens),
        brand=brand,
        size_qty=size_qty,
        size_unit=size_unit,
        pack=pack,
    )


def unit_price(price: int, product: NormalizedProduct) -> float | None:
    """Precio por litro / kilo / unidad, útil para comparar formatos distintos."""
    if not product.size_qty or not product.size_unit:
        return None
    if product.size_unit in ("ml", "g"):
        return round(price / (product.size_qty / 1000), 1)
    return round(price / product.size_qty, 1)
