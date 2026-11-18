"""Catálogo base para la fuente simulada.

Cada producto real aparece en cada tienda con un nombre distinto, como pasa en
la vida real. Incluye "trampas" a propósito (mismo producto en otro tamaño,
leche entera vs. descremada, aceite vegetal vs. girasol) para que la evaluación
de deduplicación mida algo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BaseProduct:
    key: str  # id de verdad-terreno (ground truth) para la evaluación
    category: str
    kind: str  # "aceite", "leche", ...
    variant: str  # "vegetal", "entera", ...
    brand: str
    size: str  # tal como lo escribe Lider, ej. "1 L"
    base_price: int  # CLP


def P(key, category, kind, variant, brand, size, price) -> BaseProduct:  # noqa: N802
    return BaseProduct(key, category, kind, variant, brand, size, price)


CATALOG: list[BaseProduct] = [
    P("aceite-belmont-vegetal-1l", "Despensa", "Aceite", "Vegetal", "Belmont", "1 L", 2890),
    P("aceite-belmont-vegetal-900ml", "Despensa", "Aceite", "Vegetal", "Belmont", "900 ml", 2690),
    P("aceite-chef-girasol-1l", "Despensa", "Aceite", "Girasol", "Chef", "1 L", 3190),
    P("aceite-chef-vegetal-1l", "Despensa", "Aceite", "Vegetal", "Chef", "1 L", 2990),
    P("aceite-natura-girasol-1l", "Despensa", "Aceite", "Girasol", "Natura", "1 L", 3290),
    P("aceite-miraflores-oliva-500ml", "Despensa", "Aceite", "Oliva extra virgen", "Miraflores", "500 ml", 5990),
    P("arroz-tucapel-g1-1kg", "Despensa", "Arroz", "Grado 1 grano largo", "Tucapel", "1 kg", 1890),
    P("arroz-tucapel-g2-1kg", "Despensa", "Arroz", "Grado 2", "Tucapel", "1 kg", 1490),
    P("arroz-banquete-g1-1kg", "Despensa", "Arroz", "Grado 1 grano largo", "Banquete", "1 kg", 1690),
    P("fideos-carozzi-spaghetti5-400g", "Despensa", "Fideos", "Spaghetti 5", "Carozzi", "400 g", 1090),
    P("fideos-lucchetti-spaghetti5-400g", "Despensa", "Fideos", "Spaghetti 5", "Lucchetti", "400 g", 990),
    P("fideos-carozzi-corbata-400g", "Despensa", "Fideos", "Corbatas", "Carozzi", "400 g", 1150),
    P("azucar-iansa-1kg", "Despensa", "Azúcar", "Blanca", "Iansa", "1 kg", 1490),
    P("azucar-iansa-flor-1kg", "Despensa", "Azúcar", "Flor", "Iansa", "1 kg", 1790),
    P("harina-selecta-1kg", "Despensa", "Harina", "Sin polvos de hornear", "Selecta", "1 kg", 1290),
    P("cafe-nescafe-tradicion-170g", "Desayuno", "Café", "Tradición instantáneo", "Nescafé", "170 g", 6490),
    P("cafe-nescafe-fina-170g", "Desayuno", "Café", "Fina selección instantáneo", "Nescafé", "170 g", 6990),
    P("avena-quaker-tradicional-800g", "Desayuno", "Avena", "Tradicional", "Quaker", "800 g", 2990),
    P("leche-soprole-entera-1l", "Lácteos", "Leche", "Entera", "Soprole", "1 L", 1190),
    P("leche-soprole-descremada-1l", "Lácteos", "Leche", "Descremada", "Soprole", "1 L", 1190),
    P("leche-colun-entera-1l", "Lácteos", "Leche", "Entera", "Colun", "1 L", 1150),
    P("leche-colun-semidescremada-1l", "Lácteos", "Leche", "Semidescremada", "Colun", "1 L", 1150),
    P("leche-loncoleche-entera-1l", "Lácteos", "Leche", "Entera", "Loncoleche", "1 L", 1090),
    P("mantequilla-colun-250g", "Lácteos", "Mantequilla", "Con sal", "Colun", "250 g", 2690),
    P("yoghurt-soprole-frutilla-6x120g", "Lácteos", "Yoghurt", "Batido frutilla", "Soprole", "6 x 120 g", 2490),
    P("queso-colun-gauda-250g", "Lácteos", "Queso", "Gauda laminado", "Colun", "250 g", 3290),
    P("huevos-blancos-12un", "Frescos", "Huevos", "Blancos extra", "Dos Álamos", "12 un", 3990),
    P("pan-ideal-molde-blanco-560g", "Panadería", "Pan de molde", "Blanco", "Ideal", "560 g", 2390),
    P("pan-ideal-molde-integral-560g", "Panadería", "Pan de molde", "Integral", "Ideal", "560 g", 2590),
    P("bebida-cocacola-original-3l", "Bebidas", "Bebida", "Original", "Coca Cola", "3 L", 3290),
    P("bebida-cocacola-zero-3l", "Bebidas", "Bebida", "Zero", "Coca Cola", "3 L", 3290),
    P("bebida-cocacola-original-6x350ml", "Bebidas", "Bebida", "Original lata", "Coca Cola", "6 x 350 ml", 4990),
    P("agua-cachantun-singas-1.6l", "Bebidas", "Agua mineral", "Sin gas", "Cachantun", "1,6 L", 990),
    P("agua-cachantun-congas-1.6l", "Bebidas", "Agua mineral", "Con gas", "Cachantun", "1,6 L", 990),
    P("jugo-watts-naranja-1.5l", "Bebidas", "Néctar", "Naranja", "Watts", "1,5 L", 1590),
    P("detergente-omo-liquido-3l", "Limpieza", "Detergente líquido", "Matic", "Omo", "3 L", 9990),
    P("detergente-ariel-liquido-3l", "Limpieza", "Detergente líquido", "Concentrado", "Ariel", "3 L", 10490),
    P("papel-confort-doblehoja-12un", "Limpieza", "Papel higiénico", "Doble hoja", "Confort", "12 un", 6990),
    P("papel-elite-doblehoja-12un", "Limpieza", "Papel higiénico", "Doble hoja", "Elite", "12 un", 7490),
    P("papel-noble-doblehoja-12un", "Limpieza", "Papel higiénico", "Doble hoja", "Noble", "12 un", 6490),
]


def _size_variants(size: str) -> dict[str, str]:
    """Cada tienda escribe el tamaño a su manera."""
    s = size
    return {
        "lider": s,
        "jumbo": s.replace(" L", "lt")
        .replace(" ml", "ml")
        .replace(" kg", "kg")
        .replace(" g", "g")
        .replace(" un", " un"),
        "unimarc": s.replace(" L", " LITRO").replace(" kg", " KILO").replace(" g", " GRS").replace(" un", " UNIDADES"),
        "santa-isabel": s.replace(" g", " gr").replace(" L", " lt"),
    }


# Abreviaturas y estilo propios de cada tienda (lo que hace difícil deduplicar).
STORE_ALIASES: dict[str, dict[str, str]] = {
    "lider": {},
    "jumbo": {
        "Grado 1 grano largo": "G1 Grano Largo",
        "Grado 2": "G2",
        "Spaghetti 5": "Spaghetti N°5",
        "Tradición instantáneo": "Tradicion",
        "Fina selección instantáneo": "Fina Seleccion",
        "Néctar": "Nectar",
        "Detergente líquido": "Detergente Liq.",
        "Original lata": "Lata",
    },
    "unimarc": {
        "Semidescremada": "Semidesc",
        "Descremada": "Descrem",
        "Oliva extra virgen": "Oliva EV",
        "Sin gas": "S/Gas",
        "Con gas": "C/Gas",
        "Pan de molde": "Pan Molde",
        "Papel higiénico": "Papel Hig",
        "Batido frutilla": "Frutilla",
        "Sin polvos de hornear": "S/Polvos",
    },
    "santa-isabel": {
        "Doble hoja": "DH",
        "Gauda laminado": "gauda laminas",
        "Grado 1 grano largo": "grado 1",
        "Blancos extra": "blanco extra",
        " instantáneo": "",
    },
}


def _alias(text: str, store: str) -> str:
    for src, dst in STORE_ALIASES[store].items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def store_name(p: BaseProduct, store: str) -> str:
    size = _size_variants(p.size)[store]
    kind, variant = _alias(p.kind, store), _alias(p.variant, store)
    if store == "lider":
        return f"{kind} {variant} {p.brand} {size}"
    if store == "jumbo":
        return f"{kind} {p.brand} {variant} {size}"
    if store == "unimarc":
        return f"{kind} {variant} {p.brand} {size}".upper()
    # santa-isabel: tamaño antes de la marca
    return f"{kind} {variant.lower()} {size} {p.brand}"


STORES: dict[str, str] = {
    "lider": "Lider",
    "jumbo": "Jumbo",
    "unimarc": "Unimarc",
    "santa-isabel": "Santa Isabel",
}

# Factor de precio por tienda (posicionamiento).
STORE_PRICE_FACTOR: dict[str, float] = {
    "lider": 0.96,
    "jumbo": 1.06,
    "unimarc": 1.00,
    "santa-isabel": 1.02,
}
