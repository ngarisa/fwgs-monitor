"""Email notifier via SMTP.

Sends product notifications to one or more recipients using SMTP.
Supports STARTTLS (587) or SSL (465). Keep bodies short & link out.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable

from . import config
from . import autocheckout
from .scraper import Product

logger = logging.getLogger(__name__)


def _build_subject(product: Product, event_type: str) -> str:
    tag = {"new": "New", "available": "Back in Stock", "removed": "Removed"}.get(event_type, "Update")
    return f"{config.EMAIL_SUBJECT_PREFIX} {tag}: {product.name}"


def _build_bodies(product: Product, event_type: str) -> tuple[str, str]:
    """Return (plain_text, html) bodies."""
    price = f"${float(product.price or 0):.2f}"
    qty = int(product.quantity or 0)
    title = product.name or "Unknown product"

    if event_type == "available":
        heading = "Back in Stock"
        lines = [f"Price: {price}", f"Current quantity: {qty}"]
    elif event_type == "removed":
        heading = "Removed from Catalog"
        lines = ["This product is no longer listed on the site."]
    else:
        heading = "New Product"
        lines = [f"Price: {price}", f"Available quantity: {qty}"]

    # Add checkout information
    try:
        if autocheckout._matches_keywords(product) and autocheckout._should_attempt_manual(product):
            lines.append("")
            lines.append("🤖 Auto-checkout enabled (keyword match)")
        elif autocheckout.should_offer_manual_checkout(product, event_type):
            lines.append("")
            lines.append("👤 Manual checkout available")
            lines.append(f"� Fast checkout: http://127.0.0.1:8888/checkout/{product.id}")
            lines.append("⚡ Click the link above to instantly trigger checkout!")
    except Exception:
        # Don't let checkout logic errors break notifications
        pass

    url = product.page_url or config.BASE_URL
    img = product.image_url or ""

    # --- Plain text body
    plain = (
        f"{heading}: {title}\n\n"
        + "\n".join(lines)
        + f"\n\nLink: {url}\n"
    )

    # --- HTML body (avoid nested f-strings)
    li_html = "".join("<li>{}</li>".format(l) for l in lines)
    img_html = '<p><img src="{}" alt="image" style="max-width:480px;"></p>'.format(img) if img else ""

    html = (
        "<html>"
        "<body>"
        "<h3>{heading}: {title}</h3>"
        "<ul>{lis}</ul>"
        '<p><a href="{url}">Open product page</a></p>'
        "{img}"
        "</body>"
        "</html>"
    ).format(heading=heading, title=title, lis=li_html, url=url, img=img_html)

    return plain, html


def _send(msg: EmailMessage) -> None:
    required = (config.EMAIL_USERNAME, config.EMAIL_PASSWORD, config.EMAIL_FROM, config.EMAIL_TO)
    if not all(required) or not config.EMAIL_TO:
        logger.error("Email config incomplete; set EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM, EMAIL_TO")
        return

    host, port = config.EMAIL_SMTP_HOST, int(config.EMAIL_SMTP_PORT)
    try:
        if config.EMAIL_USE_TLS and port == 587:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as s:
                s.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
                s.send_message(msg)
        logger.info("Email sent to %s (subject=%s)", ", ".join(config.EMAIL_TO), msg.get("Subject"))
    except Exception:
        logger.exception("Failed to send email")


def send_product_event(product: Product, event_type: str = "new") -> None:
    if not config.EMAIL_ENABLED or not config.EMAIL_TO:
        return

    subject = _build_subject(product, event_type)
    plain, html = _build_bodies(product, event_type)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM or (config.EMAIL_USERNAME or "")
    msg["To"] = ", ".join(config.EMAIL_TO)
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    _send(msg)


def send_notifications(products: Iterable[Product]) -> None:
    for p in products:
        send_product_event(p, event_type="new")
