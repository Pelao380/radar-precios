"""Modelo de datos.

Capas (estilo medallion, simplificado):
  raw_snapshots      bronze: respuesta cruda de la tienda (JSONB), reproducible
  listings           silver: ficha normalizada por (tienda, sku), con embedding
  products           gold:   producto canónico deduplicado entre tiendas
  price_observations historial: un precio por ficha y día
"""

from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings
from .matching import EMBED_DIM


class Base(DeclarativeBase):
    pass


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))


class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    observed_on: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    item_count: Mapped[int] = mapped_column(Integer)
    payload: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(200))
    clean_name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(80))
    size_qty: Mapped[float | None] = mapped_column(Float)
    size_unit: Mapped[str | None] = mapped_column(String(4))
    size_label: Mapped[str] = mapped_column(String(20), default="")
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    listings: Mapped[list[Listing]] = relationship(back_populates="product")

    __table_args__ = (
        Index("ix_products_block", "size_unit", "size_qty"),
        Index(
            "ix_products_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    sku: Mapped[str] = mapped_column(String(80))
    raw_name: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    match_score: Mapped[float | None] = mapped_column(Float)
    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date)
    product: Mapped[Product] = relationship(back_populates="listings")
    store: Mapped[Store] = relationship()

    __table_args__ = (UniqueConstraint("store_id", "sku"),)


class PriceObservation(Base):
    __tablename__ = "price_observations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    observed_on: Mapped[date] = mapped_column(Date)
    price: Mapped[int] = mapped_column(Integer)
    list_price: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("listing_id", "observed_on"),
        Index("ix_obs_day", "observed_on"),
    )


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    target_price: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("email", "product_id"),)


class AlertSent(Base):
    __tablename__ = "alerts_sent"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("alert_subscriptions.id", ondelete="CASCADE"))
    observed_on: Mapped[date] = mapped_column(Date)
    price: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(120))

    # idempotencia: como mucho una alerta por suscripción y día
    __table_args__ = (UniqueConstraint("subscription_id", "observed_on"),)


def sqlalchemy_url(url: str) -> str:
    """Neon/Render/Heroku entregan `postgres://` o `postgresql://`; usamos el driver psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


engine = create_engine(sqlalchemy_url(settings.database_url), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# Precio actual por producto y tienda (última observación de cada ficha).
CURRENT_PRICES_VIEW = """
CREATE OR REPLACE VIEW current_prices AS
SELECT DISTINCT ON (l.id)
       l.product_id, l.id AS listing_id, s.slug AS store, s.name AS store_name,
       o.price, o.list_price, o.observed_on, l.url
FROM listings l
JOIN stores s ON s.id = l.store_id
JOIN price_observations o ON o.listing_id = l.id
ORDER BY l.id, o.observed_on DESC;
"""

# Estadísticas de 90 días por producto (todas las tiendas). Se refresca tras cada ETL.
PRODUCT_STATS_MV = """
CREATE MATERIALIZED VIEW IF NOT EXISTS product_stats AS
WITH ref AS (SELECT COALESCE(MAX(observed_on), CURRENT_DATE) AS today FROM price_observations),
best_today AS (
    SELECT l.product_id, MIN(o.price) AS best_price
    FROM price_observations o JOIN listings l ON l.id = o.listing_id, ref
    WHERE o.observed_on = ref.today
    GROUP BY l.product_id
),
daily_best AS (
    SELECT l.product_id, o.observed_on, MIN(o.price) AS price
    FROM price_observations o JOIN listings l ON l.id = o.listing_id, ref
    WHERE o.observed_on > ref.today - 90
    GROUP BY l.product_id, o.observed_on
)
SELECT d.product_id,
       b.best_price,
       MIN(d.price) FILTER (WHERE d.observed_on < ref.today) AS min_90d_before_today,
       MIN(d.price) AS min_90d,
       MAX(d.price) AS max_90d,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY d.price)
           FILTER (WHERE d.observed_on > ref.today - 30) AS median_30d,
       COUNT(*) AS days_observed
FROM daily_best d
JOIN best_today b USING (product_id)
CROSS JOIN ref
GROUP BY d.product_id, b.best_price;
CREATE UNIQUE INDEX IF NOT EXISTS ux_product_stats ON product_stats (product_id);
"""


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(CURRENT_PRICES_VIEW))
        for stmt in PRODUCT_STATS_MV.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt))


def refresh_stats() -> None:
    with engine.begin() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY product_stats"))
