import pytest

from radar.normalize import normalize, unit_price


@pytest.mark.parametrize(
    "raw, qty, unit",
    [
        ("Aceite Vegetal Belmont 1 L", 1000, "ml"),
        ("Aceite Belmont Vegetal 1lt", 1000, "ml"),
        ("ACEITE VEGETAL BELMONT 1 LITRO", 1000, "ml"),
        ("Aceite Belmont 900 ml", 900, "ml"),
        ("Agua Cachantun 1,6 L", 1600, "ml"),
        ("Arroz Tucapel 1 KILO", 1000, "g"),
        ("Fideos 400 GRS", 400, "g"),
        ("Coca Cola Lata 6 x 350 ml", 2100, "ml"),
        ("Yoghurt 6x120g", 720, "g"),
        ("Papel Higiénico 12 UNIDADES", 12, "un"),
        ("Producto sin tamaño", None, None),
    ],
)
def test_parse_size(raw, qty, unit):
    p = normalize(raw)
    assert p.size_qty == qty
    assert p.size_unit == unit


def test_same_product_different_stores_normalizes_equal():
    names = [
        "Aceite Vegetal Belmont 1 L",
        "Aceite Belmont Vegetal 1lt",
        "ACEITE VEGETAL BELMONT 1 LITRO",
        "Aceite vegetal 1 lt Belmont",
    ]
    keys = {(p.brand, p.clean_name, p.size_qty) for p in map(normalize, names)}
    assert keys == {("belmont", "aceite vegetal", 1000)}


def test_brand_hint_wins():
    assert normalize("Leche entera 1 L", brand_hint="Colún").brand == "colun"


def test_synonyms_and_accents():
    p = normalize("Aceite MARAVILLA Chef 1 L")
    assert p.clean_name == "aceite girasol"


def test_numbers_that_are_not_sizes_are_kept():
    # bug real encontrado por la evaluación: "grado 1" y "grado 2" se fusionaban
    assert normalize("Arroz Grado 1 Tucapel 1 kg").clean_name != normalize("Arroz Grado 2 Tucapel 1 kg").clean_name


def test_slash_abbreviations():
    assert "sin" in normalize("AGUA MINERAL S/GAS 1,6 L").clean_name.split()
    assert "con" in normalize("AGUA MINERAL C/GAS 1,6 L").clean_name.split()


def test_size_label():
    assert normalize("Bebida 3 L").size_label == "3 L"
    assert normalize("Queso 250 g").size_label == "250 g"


def test_unit_price_per_liter():
    assert unit_price(2890, normalize("Aceite 900 ml")) == pytest.approx(3211.1)
    assert unit_price(1000, normalize("Sin tamaño")) is None
