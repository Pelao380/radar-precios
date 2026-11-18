"""API HTTP (FastAPI) que consume el dashboard Next.js."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from . import queries
from .config import settings
from .db import AlertSubscription, SessionLocal
from .search import search as run_search

app = FastAPI(title="Radar de precios", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_session() -> Iterator[Session]:
    with SessionLocal.begin() as session:
        yield session


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    return {"ok": True}


@app.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    return queries.overview(session)


@app.get("/products")
def products(
    q: str | None = None,
    limit: int = Query(60, le=200),
    session: Session = Depends(get_session),
) -> list[dict]:
    return queries.list_products(session, q, limit)


@app.get("/products/{product_id}")
def product(product_id: int, session: Session = Depends(get_session)) -> dict:
    detail = queries.product_detail(session, product_id)
    if detail is None:
        raise HTTPException(404, "producto no encontrado")
    return detail


@app.get("/deals")
def deals(limit: int = Query(12, le=50), session: Session = Depends(get_session)) -> list[dict]:
    return queries.deals(session, limit, settings.alert_min_drop_pct)


class SearchBody(BaseModel):
    query: str = Field(min_length=2, max_length=300)


@app.post("/search")
def search(body: SearchBody, session: Session = Depends(get_session)) -> dict:
    return run_search(session, body.query)


class AlertBody(BaseModel):
    email: EmailStr
    product_id: int
    target_price: int | None = Field(default=None, gt=0)


@app.post("/alerts", status_code=201)
def subscribe(body: AlertBody, session: Session = Depends(get_session)) -> dict:
    if queries.product_detail(session, body.product_id) is None:
        raise HTTPException(404, "producto no encontrado")
    stmt = insert(AlertSubscription).values(
        email=body.email, product_id=body.product_id, target_price=body.target_price, active=True
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["email", "product_id"],
        set_={"target_price": stmt.excluded.target_price, "active": True},
    )
    session.execute(stmt)
    return {"ok": True}
