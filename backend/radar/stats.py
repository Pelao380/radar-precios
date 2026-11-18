"""Estadísticas de series de precios (funciones puras)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median


@dataclass(frozen=True)
class PricePoint:
    day: date
    price: int  # CLP


@dataclass(frozen=True)
class PriceStats:
    current: int
    min_90d: int
    max_90d: int
    median_30d: float
    trend_pct_week: float  # pendiente de la regresión lineal, en % del precio por semana
    is_lowest_90d: bool
    drop_pct_vs_median: float  # positivo = más barato que la mediana de 30 días


def _window(points: Sequence[PricePoint], end: date, days: int) -> list[PricePoint]:
    start = end - timedelta(days=days)
    return [p for p in points if start < p.day <= end]


def linear_trend_pct_week(points: Sequence[PricePoint]) -> float:
    if len(points) < 2:
        return 0.0
    x0 = points[0].day
    xs = [(p.day - x0).days for p in points]
    ys = [p.price for p in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0 or my == 0:
        return 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx  # CLP por día
    return round(slope * 7 / my * 100, 2)


def compute(points: Sequence[PricePoint], today: date | None = None) -> PriceStats | None:
    if not points:
        return None
    pts = sorted(points, key=lambda p: p.day)
    today = today or pts[-1].day
    last90 = _window(pts, today, 90) or pts[-1:]
    last30 = _window(pts, today, 30) or pts[-1:]
    current = pts[-1].price
    previous90 = [p.price for p in last90[:-1]]
    med30 = float(median(p.price for p in last30))
    return PriceStats(
        current=current,
        min_90d=min(p.price for p in last90),
        max_90d=max(p.price for p in last90),
        median_30d=med30,
        trend_pct_week=linear_trend_pct_week(last30),
        is_lowest_90d=bool(previous90) and current < min(previous90),
        drop_pct_vs_median=round((med30 - current) / med30 * 100, 1) if med30 else 0.0,
    )


@dataclass(frozen=True)
class DropAlert:
    reason: str
    current: int
    reference: float


def detect_drop(
    stats: PriceStats,
    min_drop_pct: float = 10.0,
    target_price: int | None = None,
) -> DropAlert | None:
    """Decide si una serie merece alerta. Orden de prioridad:
    1. el usuario fijó un precio objetivo y se alcanzó;
    2. precio más bajo de los últimos 90 días;
    3. caída >= `min_drop_pct` respecto a la mediana de 30 días.
    """
    if target_price is not None and stats.current <= target_price:
        return DropAlert("precio objetivo alcanzado", stats.current, target_price)
    if stats.is_lowest_90d:
        return DropAlert("mínimo de 90 días", stats.current, stats.min_90d)
    if stats.drop_pct_vs_median >= min_drop_pct:
        return DropAlert(
            f"bajó {stats.drop_pct_vs_median:.0f}% vs. mediana 30 días",
            stats.current,
            stats.median_30d,
        )
    return None
