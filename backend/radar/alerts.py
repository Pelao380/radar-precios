"""Alertas de caída de precio por correo."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .config import settings
from .db import AlertSent, AlertSubscription, Product
from .queries import best_daily_series
from .stats import compute, detect_drop

log = logging.getLogger(__name__)


def _fmt_clp(n: float) -> str:
    return "$" + f"{int(n):,}".replace(",", ".")


def send_email(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_user:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def evaluate_alerts(session: Session, send=send_email) -> int:
    """Revisa todas las suscripciones activas y envía las alertas nuevas.

    Idempotente: `alerts_sent` tiene UNIQUE(subscription_id, observed_on), y el
    correo solo se envía si el INSERT realmente insertó una fila.
    """
    sent = 0
    subs = session.scalars(select(AlertSubscription).where(AlertSubscription.active)).all()
    for sub in subs:
        series = best_daily_series(session, sub.product_id)
        stats = compute(series)
        if stats is None:
            continue
        alert = detect_drop(stats, settings.alert_min_drop_pct, sub.target_price)
        if alert is None:
            continue
        inserted = session.execute(
            insert(AlertSent)
            .values(subscription_id=sub.id, observed_on=series[-1].day, price=alert.current, reason=alert.reason)
            .on_conflict_do_nothing()
            .returning(AlertSent.id)
        ).scalar_one_or_none()
        if inserted is None:
            continue
        product = session.get(Product, sub.product_id)
        store = session.execute(
            text("SELECT store_name FROM current_prices WHERE product_id = :id ORDER BY price LIMIT 1"),
            {"id": sub.product_id},
        ).scalar_one_or_none()
        body = (
            f"{product.canonical_name}: {alert.reason}.\n\n"
            f"Precio actual: {_fmt_clp(alert.current)} en {store}\n"
            f"Referencia: {_fmt_clp(alert.reference)}\n"
            f"Mínimo 90 días: {_fmt_clp(stats.min_90d)}\n\n"
            f"Ver historial: {settings.public_web_url}/productos/{product.id}\n"
        )
        try:
            send(sub.email, f"📉 {product.canonical_name} a {_fmt_clp(alert.current)}", body)
            sent += 1
        except OSError as exc:
            # si falla el SMTP, se deshace el registro para reintentar en la próxima corrida
            log.warning("no se pudo enviar alerta %s: %s", sub.id, exc)
            session.execute(text("DELETE FROM alerts_sent WHERE id = :id"), {"id": inserted})
    return sent
