"""Discord webhook notifier.

Sends product notifications to a Discord channel via webhook.
If DISCORD_ATTACH_IMAGES=true, images are uploaded as attachments
and referenced via attachment://, which bypasses hotlink issues.
"""
from __future__ import annotations

import io
import json
import logging
import mimetypes
from typing import Iterable, Optional
from urllib.parse import urlparse

import requests

from .config import BASE_URL, DISCORD_WEBHOOK_URL, DISCORD_ATTACH_IMAGES
from .scraper import Product
from .utils import get_http_session, retryable_request
from . import autocheckout
from . import fast_checkout
from . import autocheckout

logger = logging.getLogger(__name__)


@retryable_request
def _post(session: requests.Session, url: str, **kwargs) -> requests.Response:
    return session.post(url, **kwargs)


def _guess_filename_and_mime(url: str, fallback_name: str = "image") -> tuple[str, str]:
    """
    Guess a safe filename and mime type from a URL.
    Defaults to .jpg if unknown.
    """
    parsed = urlparse(url)
    name = (parsed.path.rsplit("/", 1)[-1] or fallback_name).split("?")[0].split("#")[0]
    if "." not in name:
        name += ".jpg"
    mime = mimetypes.guess_type(name)[0] or "image/jpeg"
    return name, mime


def _download_image_bytes(session: requests.Session, url: str, *, max_bytes: int = 8 * 1024 * 1024) -> tuple[bytes, str, str] | None:
    """
    Fetch image bytes (capped) and return (bytes, filename, mime).
    Returns None on failure.
    """
    try:
        headers = {
            # Pretend to be a regular browser to avoid basic hotlink blocks
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        }
        with session.get(url, headers=headers, timeout=20, stream=True) as resp:
            if resp.status_code != 200:
                logger.debug("Image download failed (%s): HTTP %s", url, resp.status_code)
                return None
            data = io.BytesIO()
            total = 0
            for chunk in resp.iter_content(8192):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    logger.debug("Image too large (> %d bytes): %s", max_bytes, url)
                    return None
                data.write(chunk)
            b = data.getvalue()
        filename, mime = _guess_filename_and_mime(url)
        return b, filename, mime
    except Exception:
        logger.exception("Failed to download image: %s", url)
        return None


def _build_embed(product: Product, event_type: str = "new", *, use_attachment: bool = False, attachment_name: str | None = None) -> dict:
    title = product.name or "Unknown product"
    desc_lines: list[str] = []

    if event_type == "removed":
        title = f"Removed: {product.name}"
        desc_lines.append("This product is no longer listed on the site.")
    elif event_type == "available":
        title = f"Back in Stock: {product.name}"
        desc_lines.append(f"Price: ${float(product.price or 0):.2f}")
        desc_lines.append(f"Current quantity: {int(product.quantity or 0)}")
    elif event_type == "coming_soon":
        title = f"Coming Soon: {product.name}"
        # price may or may not be present; show if known
        if (product.price or 0) > 0:
            desc_lines.append(f"Expected price: ${float(product.price or 0):.2f}")
        desc_lines.append("Watch this page for when it goes live.")
    else:
        desc_lines.append(f"Price: ${float(product.price or 0):.2f}")
        desc_lines.append(f"Available quantity: {int(product.quantity or 0)}")

    # Add checkout information
    try:
        if autocheckout._matches_keywords(product) and autocheckout._should_attempt_manual(product):
            desc_lines.append("")
            desc_lines.append("🤖 **Auto-checkout enabled** (keyword match)")
        elif autocheckout.should_offer_manual_checkout(product, event_type):
            desc_lines.append("")
            desc_lines.append("👤 **Manual checkout available**")
            
            # Add fast checkout URL
            fast_url = fast_checkout.get_checkout_url(product.id)
            if fast_url:
                desc_lines.append(f"🔗 **[⚡ INSTANT CHECKOUT]({fast_url})**")
                desc_lines.append("↑ Click above for instant checkout ↑")
    except Exception:
        # Don't let checkout logic errors break notifications
        pass

    embed = {
        "title": title,
        "url": product.page_url,
        "description": "\n".join(desc_lines),
    }

    img_url = (product.image_url or "").strip()
    if use_attachment and attachment_name:
        embed["image"] = {"url": f"attachment://{attachment_name}"}
    elif img_url:
        embed["image"] = {"url": img_url}

    return embed


def send_product_event(
    product: Product,
    event_type: str = "new",
    webhook_url: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> None:
    if webhook_url is None:
        webhook_url = DISCORD_WEBHOOK_URL
    if not webhook_url:
        logger.error("Discord webhook URL is not configured. Cannot send notification.")
        return

    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    try:
        # Try attachment route if enabled and we have a URL to fetch
        if DISCORD_ATTACH_IMAGES and product.image_url:
            dl = _download_image_bytes(session, product.image_url)
            if dl:
                data, filename, mime = dl
                embed = _build_embed(product, event_type, use_attachment=True, attachment_name=filename)
                payload = {"embeds": [embed]}
                files = { "files[0]": (filename, data, mime) }
                logger.info("Sending %s notification (with attachment) for %s (id=%s)", event_type, product.name, product.id)
                _post(session, webhook_url, data={"payload_json": json.dumps(payload)}, files=files)
                return
            else:
                logger.debug("Falling back to direct image URL for %s", product.id)

        # Fallback: regular embed with direct URL
        payload = {"embeds": [_build_embed(product, event_type)]}
        logger.info("Sending %s notification for product %s (id=%s)", event_type, product.name, product.id)
        _post(session, webhook_url, json=payload)

                # ⬇️ NEW: kick off auto-checkout (honors your config flags)
        try:
            autocheckout.try_autocheckout(product, event_type)
        except Exception:
            logger.exception("Auto-checkout hook failed for %s (%s)", product.name, event_type)

    finally:
        if close_session:
            session.close()


def send_notifications(
    products: Iterable[Product],
    webhook_url: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> None:
    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True
    try:
        for product in products:
            send_product_event(product, event_type="new", webhook_url=webhook_url, session=session)
    finally:
        if close_session:
            session.close()

def _absolute_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    # make relative paths absolute against BASE_URL
    return BASE_URL.rstrip("/") + "/" + u.lstrip("/")


def send_release_event(
    card,
    event_type: str = "release",     # "release" (new card), "live" (now shopable)
    webhook_url: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> None:
    if webhook_url is None:
        webhook_url = DISCORD_WEBHOOK_URL
    if not webhook_url:
        logger.error("Discord webhook URL not configured.")
        return

    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    try:
        title_prefix = "Now Live" if event_type == "live" else "New Release Posted"
        title = f"{title_prefix}: {getattr(card, 'title', '') or 'Release'}"
        desc = f"Status: {getattr(card, 'status', '') or 'n/a'}"
        url = getattr(card, 'url', None)

        # Normalize image (and allow attachments, like product events)
        img_url = _absolute_url(getattr(card, 'image_url', None))

        embed = {"title": title, "description": desc}
        if url:
            embed["url"] = url

        if DISCORD_ATTACH_IMAGES and img_url:
            dl = _download_image_bytes(session, img_url)
            if dl:
                data, filename, mime = dl
                embed["image"] = {"url": f"attachment://{filename}"}
                payload = {"embeds": [embed]}
                files = {"files[0]": (filename, data, mime)}
                logger.info("Sending %s release notification (with attachment): %s", event_type, title)
                _post(session, webhook_url, data={"payload_json": json.dumps(payload)}, files=files)
                return
            else:
                logger.debug("Release: image download failed; falling back to direct URL.")

        if img_url:
            embed["image"] = {"url": img_url}

        payload = {"embeds": [embed]}
        logger.info("Sending %s release notification: %s", event_type, title)
        _post(session, webhook_url, json=payload)
    finally:
        if close_session:
            session.close()

__all__ = ["send_notifications", "send_product_event", "send_release_event"]
