from datetime import date, timedelta

from radar.stats import PricePoint, compute, detect_drop, linear_trend_pct_week

D0 = date(2026, 1, 1)


def series(prices):
    return [PricePoint(D0 + timedelta(days=i), p) for i, p in enumerate(prices)]


def test_empty_series():
    assert compute([]) is None


def test_flat_series_has_no_alert():
    s = compute(series([1000] * 40))
    assert s.min_90d == 1000 and s.trend_pct_week == 0
    assert not s.is_lowest_90d
    assert detect_drop(s) is None


def test_lowest_in_90_days():
    s = compute(series([1000] * 50 + [900]))
    assert s.is_lowest_90d
    assert detect_drop(s).reason == "mínimo de 90 días"


def test_min_90d_ignores_older_points():
    prices = [500] + [1000] * 100 + [990]
    s = compute(series(prices))
    assert s.min_90d == 990  # el 500 quedó fuera de la ventana
    assert s.is_lowest_90d


def test_drop_vs_median_without_new_low():
    # hubo un 700 hace 60 días, así que 850 no es mínimo, pero sí cae 15% vs. la mediana
    prices = [1000] * 20 + [700] + [1000] * 40 + [850]
    s = compute(series(prices))
    assert not s.is_lowest_90d
    alert = detect_drop(s)
    assert alert and "bajó 15%" in alert.reason


def test_target_price_has_priority():
    s = compute(series([1000] * 10 + [950]))
    assert detect_drop(s, target_price=960).reason == "precio objetivo alcanzado"


def test_trend_rising():
    assert linear_trend_pct_week(series([1000 + 10 * i for i in range(30)])) > 0
