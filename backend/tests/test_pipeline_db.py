"""Tests de integración contra PostgreSQL + pgvector.

Se ejecutan en CI (servicio pgvector/pgvector) o localmente con docker compose.
Borran y recrean todas las tablas, así que solo corren contra una base cuyo
nombre termine en `_test` (ej. `radar_test`); si no, se saltan.
"""

import os
from datetime import date

import pytest
from sqlalchemy.engine import make_url

_url = os.environ.get("DATABASE_URL", "")
_is_test_db = bool(_url) and (make_url(_url).database or "").endswith("_test")

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not _is_test_db, reason="requiere DATABASE_URL apuntando a una base *_test (los tests la borran)"
    ),
]

END = date(2026, 3, 31)


@pytest.fixture(scope="module")
def loaded_db():
    from sqlalchemy import text

    from radar.cli import backfill
    from radar.db import Base, engine, init_db

    with engine.begin() as conn:
        conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS product_stats"))
        conn.execute(text("DROP VIEW IF EXISTS current_prices"))
    Base.metadata.drop_all(engine)
    init_db()
    backfill(days=45, end=END)
    return END


@pytest.fixture
def session(loaded_db):
    from radar.db import SessionLocal

    with SessionLocal.begin() as s:
        yield s


def test_dedup_across_stores(session):
    from sqlalchemy import text

    products = session.execute(text("SELECT COUNT(*) FROM products")).scalar()
    listings = session.execute(text("SELECT COUNT(*) FROM listings")).scalar()
    # 40 productos reales x 4 tiendas = 160 fichas; la deduplicación debe agrupar la mayoría
    assert listings == 160
    assert 40 <= products <= 56
    # ningún producto canónico mezcla variantes en conflicto
    mixed = session.execute(
        text(
            """
            SELECT p.id FROM products p JOIN listings l ON l.product_id = p.id
            GROUP BY p.id HAVING COUNT(DISTINCT l.store_id) < COUNT(*)
            """
        )
    ).all()
    assert mixed == []  # nunca dos fichas de la misma tienda en un mismo producto


def test_reprocessing_snapshot_is_idempotent(session):
    from sqlalchemy import text

    from radar.etl import process_snapshot

    before = session.execute(text("SELECT COUNT(*) FROM price_observations")).scalar()
    snap_id = session.execute(text("SELECT MAX(id) FROM raw_snapshots")).scalar()
    process_snapshot(session, snap_id)
    after = session.execute(text("SELECT COUNT(*) FROM price_observations")).scalar()
    assert before == after


def test_product_detail_and_stats(session):
    from radar import queries

    rows = queries.list_products(session, q="aceite")
    assert rows and all("aceite" in r["name"].lower() for r in rows)
    detail = queries.product_detail(session, rows[0]["id"])
    assert detail["offers"] and detail["series"] and detail["stats"]["min_90d"] <= detail["stats"]["current"]


def test_natural_language_search(session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from radar.search import search

    res = search(session, "¿dónde está más barato el aceite de 1 L esta semana?")
    assert res["results"], res
    assert all("aceite" in r["canonical_name"].lower() for r in res["results"])
    assert all(r["size_label"] == "1 L" for r in res["results"])
    prices = [r["last_price"] for r in res["results"]]
    assert prices == sorted(prices)
    assert "más barato" in res["answer"]


def test_alerts_are_sent_once_per_day(session):
    from radar import queries
    from radar.alerts import evaluate_alerts
    from radar.db import AlertSubscription

    pid = queries.list_products(session, q="leche")[0]["id"]
    session.add(AlertSubscription(email="test@example.com", product_id=pid, target_price=10_000_000))
    session.flush()
    outbox = []
    send = lambda to, subject, body: outbox.append((to, subject))  # noqa: E731
    assert evaluate_alerts(session, send=send) >= 1
    assert evaluate_alerts(session, send=send) == 0  # idempotente
    assert outbox[0][0] == "test@example.com"


def test_api_endpoints(loaded_db):
    from fastapi.testclient import TestClient

    from radar.api import app

    c = TestClient(app)
    assert c.get("/health").json() == {"ok": True}
    ov = c.get("/overview").json()
    assert ov["listings"] == 160 and ov["last_day"] == END.isoformat()
    assert isinstance(c.get("/deals").json(), list)
    pid = c.get("/products", params={"q": "arroz"}).json()[0]["id"]
    assert c.get(f"/products/{pid}").status_code == 200
    assert c.get("/products/999999").status_code == 404
    assert c.post("/alerts", json={"email": "no-es-correo", "product_id": pid}).status_code == 422
    assert c.post("/alerts", json={"email": "a@example.com", "product_id": pid}).status_code == 201


def test_run_once_adds_a_day_without_queue(loaded_db):
    from datetime import timedelta

    from sqlalchemy import text

    from radar.cli import run_once
    from radar.db import SessionLocal

    next_day = loaded_db + timedelta(days=1)
    assert run_once(next_day) == 0
    with SessionLocal() as s:
        last = s.execute(text("SELECT MAX(observed_on) FROM price_observations")).scalar()
        listings = s.execute(text("SELECT COUNT(*) FROM listings")).scalar()
    assert last == next_day
    assert listings == 160  # mismo catálogo: no crea fichas ni productos nuevos
