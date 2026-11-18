from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "postgresql+psycopg://radar:radar@localhost:5432/radar")
    )
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL", "redis://localhost:6379/0"))
    # fuente por tienda: "simulated" (demo) o "vtex" (requiere VTEX_BASE_URL_<TIENDA>)
    source_mode: str = field(default_factory=lambda: _env("SOURCE_MODE", "simulated"))
    scrape_cron_hours: int = field(default_factory=lambda: int(_env("SCRAPE_EVERY_HOURS", "6")))
    http_cache_ttl: int = field(default_factory=lambda: int(_env("HTTP_CACHE_TTL", "1800")))
    http_rate_per_minute: int = field(default_factory=lambda: int(_env("HTTP_RATE_PER_MINUTE", "20")))
    alert_min_drop_pct: float = field(default_factory=lambda: float(_env("ALERT_MIN_DROP_PCT", "10")))
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST", "localhost"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "1025")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD", ""))
    mail_from: str = field(default_factory=lambda: _env("MAIL_FROM", "radar@localhost"))
    public_web_url: str = field(default_factory=lambda: _env("PUBLIC_WEB_URL", "http://localhost:3000"))
    cors_origins: str = field(default_factory=lambda: _env("CORS_ORIGINS", "http://localhost:3000"))


settings = Settings()
