"""Cliente HTTP "educado" para scrapers: caché, límite por dominio y reintentos.

- Caché en Redis (SETEX) por URL: si el job se reintenta o se dispara dos
  veces, no vuelve a golpear a la tienda.
- Rate limit por dominio con ventana fija en Redis (INCR + EXPIRE). Es compartido
  entre todos los workers de Celery, a diferencia de `rate_limit` de Celery,
  que es por worker.
- Los errores 429/5xx levantan `RetryableHTTPError`, que la tarea Celery
  reintenta con backoff exponencial.
"""

from __future__ import annotations

import hashlib
import json
import time
from urllib.parse import urlparse

import httpx
import redis

from .config import settings

USER_AGENT = "RadarPrecios/0.1 (+proyecto academico; contacto en README)"


class RetryableHTTPError(Exception):
    pass


class RateLimited(RetryableHTTPError):
    def __init__(self, wait_s: float):
        super().__init__(f"rate limit local, reintentar en {wait_s:.0f}s")
        self.wait_s = wait_s


class PoliteClient:
    def __init__(
        self,
        r: redis.Redis | None = None,
        per_minute: int | None = None,
        cache_ttl: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.r = r or redis.Redis.from_url(settings.redis_url)
        self.per_minute = per_minute or settings.http_rate_per_minute
        self.cache_ttl = cache_ttl if cache_ttl is not None else settings.http_cache_ttl
        self.http = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=20,
            transport=transport,
            follow_redirects=True,
        )

    def _acquire(self, domain: str) -> None:
        window = int(time.time() // 60)
        key = f"rl:{domain}:{window}"
        n = self.r.incr(key)
        if n == 1:
            self.r.expire(key, 61)
        if n > self.per_minute:
            raise RateLimited(60 - time.time() % 60)

    def get_json(self, url: str, params: dict | None = None):
        cache_key = "http:" + hashlib.sha256(f"{url}|{sorted((params or {}).items())}".encode()).hexdigest()
        cached = self.r.get(cache_key)
        if cached is not None:
            return json.loads(cached)

        self._acquire(urlparse(url).netloc)
        resp = self.http.get(url, params=params)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise RetryableHTTPError(f"{resp.status_code} en {url}")
        resp.raise_for_status()
        data = resp.json()
        if self.cache_ttl:
            self.r.set(cache_key, json.dumps(data), ex=self.cache_ttl)
        return data
