import httpx
import pytest

fakeredis = pytest.importorskip("fakeredis")

from radar.http import PoliteClient, RateLimited, RetryableHTTPError  # noqa: E402
from radar.sources.vtex import parse_vtex_products  # noqa: E402


def make_client(handler, per_minute=10, ttl=60):
    return PoliteClient(
        r=fakeredis.FakeRedis(), per_minute=per_minute, cache_ttl=ttl, transport=httpx.MockTransport(handler)
    )


def test_cache_avoids_second_request():
    calls = []

    def handler(req):
        calls.append(req.url)
        return httpx.Response(200, json=[{"ok": 1}])

    c = make_client(handler)
    assert c.get_json("https://tienda.test/api", {"q": "a"}) == [{"ok": 1}]
    assert c.get_json("https://tienda.test/api", {"q": "a"}) == [{"ok": 1}]
    assert len(calls) == 1


def test_rate_limit_per_domain():
    c = make_client(lambda req: httpx.Response(200, json=[]), per_minute=2, ttl=0)
    c.get_json("https://tienda.test/a")
    c.get_json("https://tienda.test/b")
    with pytest.raises(RateLimited):
        c.get_json("https://tienda.test/c")
    # otro dominio tiene su propio presupuesto
    c.get_json("https://otra.test/a")


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_errors_are_retryable(status):
    c = make_client(lambda req: httpx.Response(status))
    with pytest.raises(RetryableHTTPError):
        c.get_json("https://tienda.test/x")


def test_parse_vtex_products():
    items = [
        {
            "productName": "Aceite Belmont",
            "brand": "Belmont",
            "link": "https://tienda.test/aceite/p",
            "items": [
                {
                    "itemId": "123",
                    "nameComplete": "Aceite Vegetal Belmont 1 L",
                    "sellers": [{"commertialOffer": {"Price": 2490.0, "ListPrice": 2890.0, "AvailableQuantity": 10}}],
                },
                {"itemId": "124", "sellers": [{"commertialOffer": {"Price": 0}}]},
            ],
        }
    ]
    [listing] = parse_vtex_products(items)
    assert listing.sku == "123" and listing.price == 2490 and listing.list_price == 2890
    assert listing.brand == "Belmont"
