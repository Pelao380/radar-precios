from datetime import date

from radar.intent import parse, parse_rules
from radar.sources.simulated import SimulatedSource


def test_example_question():
    i = parse_rules("¿Dónde está más barato el aceite de 1 L esta semana?")
    assert i.product == "aceite"
    assert (i.size_qty, i.size_unit) == (1000, "ml")
    assert i.period_days == 7
    assert i.sort == "cheapest"


def test_store_price_and_period():
    i = parse_rules("leche descremada en Santa Isabel a menos de $1.200 hoy")
    assert i.product == "leche descremada"
    assert i.store == "santa-isabel"
    assert i.max_price == 1200
    assert i.period_days == 1


def test_deals_question():
    i = parse_rules("qué ofertas de café hay este mes")
    assert i.product == "cafe"
    assert i.sort == "biggest_drop"
    assert i.period_days == 30


def test_parse_without_api_key_uses_rules(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert parse("arroz 1 kg").parser == "rules"


def test_simulated_source_is_deterministic():
    a = SimulatedSource("lider").fetch(date(2026, 3, 1))
    b = SimulatedSource("lider").fetch(date(2026, 3, 1))
    assert a == b
    assert all(x.price > 0 and x.price % 10 == 0 for x in a)
