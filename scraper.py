from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence
from bs4.element import Tag
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs

from .config import (
    BASE_URL,
    CATEGORY_ID,
    ASSEMBLER_NRPP,
    ASSEMBLER_NS,
    LEGACY_CATEGORY_ID,
    RELEASE_USE_BROWSER,
    RELEASE_BROWSER_TIMEOUT_MS,
)
# scraper.py
from .config import ONLINE_EXCLUSIVE_CATEGORY_IDS

# COMING_SOON_NS is optional in config; provide a safe fallback if not defined.
try:
    from .config import COMING_SOON_NS
except Exception:
    COMING_SOON_NS = None
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    _PLAYWRIGHT_AVAILABLE = True
except Exception:
    _PLAYWRIGHT_AVAILABLE = False
    PWTimeoutError = Exception  # type: ignore

from .utils import get_http_session, retryable_request

logger = logging.getLogger(__name__)


@dataclass
class Product:
    id: str
    name: str
    price: float
    image_url: str
    page_url: str
    quantity: int
    is_online_exclusive: int = 0
    

import hashlib

@dataclass
class ReleaseCard:
    key: str           # stable key derived from URL/title
    title: str
    url: str
    image_url: str | None
    status: str        # e.g., "coming soon", "sold out", "shop now", "available", ""

@retryable_request
def _get(session: requests.Session, url: str, **kwargs: dict) -> requests.Response:
    """Thin wrapper around session.get with retry policy from utils.retryable_request."""
    return session.get(url, **kwargs)

def _build_products_endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/ccstore/v1/products"

def _build_stock_status_endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/ccstore/v1/stockStatus"

def _stable_key_from(text: str) -> str:
    t = (text or "").strip().lower()
    return hashlib.sha1(t.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _release_status_from_text(txt: str) -> str:
    t = (txt or "").lower()
    if "shop now" in t or "add to cart" in t or "buy" in t:
        return "live"
    if "coming soon" in t:
        return "coming soon"
    if "sold out" in t or "out of stock" in t:
        return "sold out"
    return ""


def fetch_release_cards(
    page_url: str,
    *,
    base_url: str = BASE_URL,
    session: Optional[requests.Session] = None,
) -> List[ReleaseCard]:
    """
    Parse the Whiskey Release landing page and return 'cards' that link to /product/... pages.

    Strategy (in order):
      1) Try both URL variants (hyphenated and %20).
      2) requests -> parse anchors/tiles/inline JSON.
      3) Playwright fallback: wait + scroll + crawl Shadow DOM + all frames.
      4) While in Playwright, sniff JSON/XHR responses and mine product links.
    """
    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    # ---------- helpers ----------

    def _parse_cards_from_html(html: str, base_url: str) -> List[ReleaseCard]:
        soup = BeautifulSoup(html, "html.parser")

        h1 = soup.find(["h1", "h2"])
        if h1:
            logger.info("Release page heading: %s", h1.get_text(strip=True)[:120])
        logger.info("Release page length: %d chars", len(html))

        candidates: list[ReleaseCard] = []
        seen_keys: set[str] = set()

        def add_card(url: str, title: str, img: Optional[str], status: str) -> None:
            abs_url = urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))
            key = "release:" + _stable_key_from(abs_url)
            if key in seen_keys:
                return
            seen_keys.add(key)
            candidates.append(
                ReleaseCard(
                    key=key,
                    title=title or abs_url,
                    url=abs_url,
                    image_url=_normalize_image_url(img, base_url) if img else None,
                    status=status or "",
                )
            )

        # 1) Direct anchors
        product_links = soup.select('a[href*="/product/"]')
        logger.info("Release: explicit product links found: %d", len(product_links))
        for a in product_links[:200]:
            href = (a.get("href") or "").strip()
            if not href:
                continue
            container = a.find_parent(["article"]) or a.find_parent(
                class_=["card", "teaser", "tile", "grid__item", "c-card", "cc-card", "cc-tile"]
            )
            title_el = (container.find(["h1", "h2", "h3", "h4"]) if container else None)
            title = (
                (title_el or a).get_text(strip=True)
                or a.get("aria-label")
                or a.get("title")
                or href
            )
            img_el = (container or a).find("img") if container else a.find("img")
            meta_img = soup.select_one('meta[property="og:image"], meta[name="og:image"]')
            img = (meta_img.get("content") if meta_img else None) or (img_el.get("src") if img_el else None)
            block_text = " ".join([
                a.get_text(" ", strip=True) or "",
                (container.get_text(" ", strip=True) if container else "")
            ])
            status = _release_status_from_text(block_text)
            add_card(href, title, img, status)

        # 2) CMS-ish tiles
        tiles = soup.select("article, .card, .teaser, .tile, .grid__item, .c-card, .cc-card, .cc-tile")
        logger.info("Release: tile-like blocks found: %d", len(tiles))
        for b in tiles:
            a = b.find("a", href=True)
            if a and "/product/" in (a.get("href") or ""):
                href = a.get("href", "")
                title_el = b.find(["h1", "h2", "h3", "h4"]) or a
                title = (title_el.get_text(strip=True) or href)
                img_el = b.find("img")
                img = img_el.get("src") if img_el else None
                status = _release_status_from_text(b.get_text(" ", strip=True))
                add_card(href, title, img, status)

        # 3) Inline JSON rescue
        if not candidates:
            json_cards = _extract_cards_from_inline_json(soup, base_url)
            if json_cards:
                logger.info("Release: recovered %d candidates from inline JSON.", len(json_cards))
                candidates = json_cards

        # Dedup by URL
        out: list[ReleaseCard] = []
        seen_urls: set[str] = set()
        for c in candidates:
            ukey = (c.url or "").lower()
            if ukey and ukey not in seen_urls:
                seen_urls.add(ukey)
                out.append(c)

        logger.info("Release: candidates parsed: %d", len(out))
        return out

    def _cards_from_simple_dicts(items: Iterable[dict], base_url: str) -> List[ReleaseCard]:
        out: list[ReleaseCard] = []
        seen: set[str] = set()

        def norm_url(u: Optional[str]) -> Optional[str]:
            if not u:
                return None
            u = u.strip()
            if not u:
                return None
            if u.startswith("http://") or u.startswith("https://"):
                return u
            return urljoin(base_url.rstrip("/") + "/", u.lstrip("/"))

        for it in items:
            url = norm_url(it.get("route") or it.get("seoUrl") or it.get("href") or it.get("url"))
            if not url or "/product/" not in url:
                continue
            title = (it.get("displayName") or it.get("title") or url).strip()
            img = it.get("primaryMediumImageURL") or it.get("primaryLargeImageURL") or it.get("img")
            status = _release_status_from_text(it.get("status") or "")
            key = "release:" + _stable_key_from(url)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                ReleaseCard(
                    key=key,
                    title=title,
                    url=url,
                    image_url=_normalize_image_url(img, base_url) if img else None,
                    status=status,
                )
            )
        return out

    def _collect_links_via_shadow_dom(page, base_url: str) -> List[ReleaseCard]:
        """Walk shadow roots in the main document to collect anchors."""
        js = r"""
        (() => {
          const results = []; const seen = new Set();
          const statusFromText = (t) => {
            const s = (t || "").toLowerCase();
            if (s.includes("shop now") || s.includes("add to cart") || s.includes("buy")) return "live";
            if (s.includes("coming soon")) return "coming soon";
            if (s.includes("sold out") || s.includes("out of stock")) return "sold out";
            return "";
          };
          const walk = (root) => {
            root.querySelectorAll('a[href*="/product/"]').forEach(a => {
              const href = a.href;
              if (!href || seen.has(href)) return;
              seen.add(href);
              const container = a.closest('article, .card, .teaser, .tile, .grid__item, .c-card, .cc-card, .cc-tile') || a;
              const titleEl = (container.querySelector("h1,h2,h3,h4") || a);
              const title = (titleEl.textContent || a.getAttribute("aria-label") || a.getAttribute("title") || href).trim();
              let img = null;
              const imgEl = container.querySelector("img");
              if (imgEl && imgEl.src) img = imgEl.src;
              const status = statusFromText(container.textContent || "");
              results.push({ href, title, img, status });
            });
            root.querySelectorAll("*").forEach(el => { if (el.shadowRoot) walk(el.shadowRoot); });
          };
          walk(document);
          return results;
        })()
        """
        items = page.evaluate(js) or []
        return _cards_from_simple_dicts(items, base_url)

    def _collect_links_from_all_frames(page, base_url: str) -> List[ReleaseCard]:
        """Run the same shadow-DOM collector in every frame/iframe."""
        cards: list[ReleaseCard] = []
        seen: set[str] = set()

        for fr in page.frames:
            try:
                items = fr.evaluate(
                    """(() => {
                        const out=[]; const seen=new Set();
                        const walk=(root)=>{
                          root.querySelectorAll('a[href*="/product/"]').forEach(a=>{
                            const href=a.href; if(!href||seen.has(href)) return; seen.add(href);
                            const c=a.closest('article, .card, .teaser, .tile, .grid__item, .c-card, .cc-card, .cc-tile')||a;
                            const tEl=(c.querySelector("h1,h2,h3,h4")||a);
                            const title=(tEl.textContent||a.getAttribute("aria-label")||a.getAttribute("title")||href).trim();
                            let img=null; const imgEl=c.querySelector("img"); if(imgEl&&imgEl.src) img=imgEl.src;
                            out.push({href, title, img, status:c.textContent||""});
                          });
                          root.querySelectorAll("*").forEach(el=>{ if(el.shadowRoot) walk(el.shadowRoot); });
                        };
                        walk(document);
                        return out;
                    })()"""
                ) or []
                for c in _cards_from_simple_dicts(items, base_url):
                    if c.key not in seen:
                        seen.add(c.key)
                        cards.append(c)
            except Exception:
                continue
        return cards

    def _sniff_links_from_network(sniffed: list[dict], base_url: str) -> List[ReleaseCard]:
        """Convert sniffed JSON blobs to cards."""
        return _cards_from_simple_dicts(sniffed, base_url)

    # build URL variants
    variants = [page_url]
    if "/whiskey%20release/" in page_url:
        variants.append(page_url.replace("/whiskey%20release/", "/whiskey-release/"))
    if "/whiskey-release/" in page_url:
        variants.append(page_url.replace("/whiskey-release/", "/whiskey%20release/"))

    try:
        for idx, url in enumerate(variants, 1):
            logger.info("Release: fetching variant %d/%d -> %s", idx, len(variants), url)

            # --- 1) plain requests path
            html = _fetch_html(session, url)
            cards: List[ReleaseCard] = []
            if html:
                parsed = _parse_cards_from_html(html, base_url)
                if parsed:
                    cards = parsed

            # --- 2) browser fallback
            if (not cards) and RELEASE_USE_BROWSER:
                logger.info("Release: trying browser fallback for %s", url)
                if _PLAYWRIGHT_AVAILABLE:
                    try:
                        from playwright.sync_api import sync_playwright
                        sniffed_items: list[dict] = []

                        def _try_parse_json(resp):
                            try:
                                ct = (resp.headers.get("content-type") or "").lower()
                                if "application/json" not in ct:
                                    return None
                                return resp.json()
                            except Exception:
                                # fallback: text then best-effort JSON
                                try:
                                    t = resp.text()
                                    if not t:
                                        return None
                                    # light heuristic: only attempt if it looks like JSON
                                    if (t.lstrip().startswith("{") and t.rstrip().endswith("}")) or \
                                       (t.lstrip().startswith("[") and t.rstrip().endswith("]")):
                                        import json as _json
                                        return _json.loads(t)
                                except Exception:
                                    return None
                                return None

                        def _mine_for_products(obj):
                            """Yield tiny dicts with route/title/image/status if present."""
                            def _iter(o):
                                if isinstance(o, dict):
                                    yield o
                                    for v in o.values():
                                        yield from _iter(v)
                                elif isinstance(o, list):
                                    for v in o:
                                        yield from _iter(v)

                            for d in _iter(obj):
                                rid = d.get("repositoryId") or \
                                      (isinstance(d.get("product"), dict) and d["product"].get("repositoryId")) or \
                                      (isinstance(d.get("sku"), dict) and d["sku"].get("repositoryId"))
                                route = d.get("route") or d.get("seoUrl") or d.get("seoUrlSlugDerived") or \
                                        (isinstance(d.get("product"), dict) and d["product"].get("route")) or \
                                        (isinstance(d.get("sku"), dict) and d["sku"].get("route"))
                                title = d.get("displayName") or \
                                        (isinstance(d.get("product"), dict) and d["product"].get("displayName")) or \
                                        (isinstance(d.get("sku"), dict) and d["sku"].get("displayName"))
                                img = d.get("primaryMediumImageURL") or d.get("primaryLargeImageURL") or \
                                      (isinstance(d.get("sku"), dict) and (d["sku"].get("primaryMediumImageURL") or d["sku"].get("primaryLargeImageURL")))
                                if (rid or route) and (route and "/product/" in str(route)):
                                    sniffed_items.append({"route": route, "displayName": title, "img": img})

                        with sync_playwright() as p:
                            browser = p.chromium.launch(headless=True)
                            ctx = browser.new_context(
                                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                                locale="en-US",
                            )

                            # Attach network sniffer
                            def _on_response(resp):
                                try:
                                    u = (resp.url or "").lower()
                                    # only sniff JSON-y endpoints that are likely to carry product lists
                                    if ("/ccstore/" in u or "/osf/" in u or "/assembler/" in u or "/content" in u or "/pages" in u) and resp.status == 200:
                                        js = _try_parse_json(resp)
                                        if js is not None:
                                            _mine_for_products(js)
                                except Exception:
                                    pass

                            ctx.on("response", _on_response)

                            page = ctx.new_page()
                            try:
                                page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded", timeout=15000)
                            except Exception:
                                pass

                            page.goto(url, wait_until="domcontentloaded", timeout=RELEASE_BROWSER_TIMEOUT_MS // 2)

                            # give the page time to load widgets / slots
                            try:
                                page.wait_for_load_state("networkidle", timeout=RELEASE_BROWSER_TIMEOUT_MS // 2)
                            except Exception:
                                pass

                            # gentle auto-scroll to trigger lazy rendering
                            try:
                                page.evaluate("""async () => {
                                  const s = (y) => new Promise(r => { window.scrollBy(0,y); requestAnimationFrame(()=>setTimeout(r,150)); });
                                  for (let i=0;i<12;i++) { await s(800); }
                                  window.scrollTo(0,0);
                                }""")
                            except Exception:
                                pass

                            # Collect via DOM (main doc)
                            dom_cards = _collect_links_via_shadow_dom(page, base_url)

                            # Collect via all frames (iframes)
                            frame_cards = _collect_links_from_all_frames(page, base_url)

                            # Convert sniffed JSON → cards
                            sniff_cards = _sniff_links_from_network(sniffed_items, base_url)

                            # Merge + dedupe
                            by_key: dict[str, ReleaseCard] = {}
                            for coll, tag in ((dom_cards, "DOM"),
                                              (frame_cards, "IFRAME"),
                                              (sniff_cards, "NET")):
                                for c in coll:
                                    by_key[c.key] = c
                            cards = list(by_key.values())

                            logger.info(
                                "Release (browser): DOM=%d, IFRAME=%d, NET=%d, total unique=%d",
                                len(dom_cards), len(frame_cards), len(sniff_cards), len(cards)
                            )

                            # If still nothing, one tiny retry after a pause
                            if not cards:
                                try:
                                    page.wait_for_timeout(1500)
                                except Exception:
                                    pass
                                dom_cards2 = _collect_links_via_shadow_dom(page, base_url)
                                frame_cards2 = _collect_links_from_all_frames(page, base_url)
                                by_key2 = {c.key: c for c in (cards + dom_cards2 + frame_cards2)}
                                cards = list(by_key2.values())
                                logger.info(
                                    "Release (browser): retry DOM+IFRAME found=%d (total unique=%d)",
                                    len(dom_cards2) + len(frame_cards2), len(cards)
                                )

                            ctx.close()
                            browser.close()
                    except Exception:
                        logger.info("Release: Playwright fallback failed.", exc_info=True)
                else:
                    logger.info("Release: Playwright not installed; skipping browser fallback.")

            if cards:
                for c in cards[:10]:
                    logger.info("Release candidate: %s | %s | %s", (c.title or "")[:80], c.status or "n/a", c.url)
                return cards

        logger.info("Release: no candidates found across all URL variants.")
        return []
    finally:
        if close_session:
            session.close()




def _parse_price(item: dict) -> float:
    sale = item.get("salePrice")
    if sale is not None:
        try:
            return float(sale)
        except (TypeError, ValueError):
            pass
    try:
        return float(item.get("listPrice", 0))
    except (TypeError, ValueError):
        return 0.0


def _normalize_image_url(src: str, base_url: str) -> str:
    """
    Turn OCC image-service URLs into direct file URLs to avoid Discord hotlink issues.
    Example:
      /ccstore/v1/images/?source=/file/v123/products/000008520_F1.jpg&width=300
    ->  /file/v123/products/000008520_F1.jpg
    """
    if not src:
        return ""
    # Make absolute for parsing
    abs_url = urljoin(base_url.rstrip("/") + "/", src.lstrip("/"))
    parsed = urlparse(abs_url)
    if parsed.path.rstrip("/").endswith("/ccstore/v1/images"):
        qs = parse_qs(parsed.query or "")
        inner = qs.get("source", [None])[0]
        if inner:
            return urljoin(base_url.rstrip("/") + "/", inner.lstrip("/"))
    return abs_url
def _iter_dicts(o):
    """Yield all dicts inside arbitrary JSON (list/dict scalars)."""
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _iter_dicts(v)
    elif isinstance(o, list):
        for v in o:
            yield from _iter_dicts(v)

def _first_nonempty(*vals) -> Optional[str]:
    for v in vals:
        if v:
            s = str(v).strip()
            if s:
                return s
    return None

def _to_abs_route(route: Optional[str], base_url: str) -> Optional[str]:
    if not route:
        return None
    r = str(route)
    if r.startswith("http://") or r.startswith("https://"):
        return r
    if not r.startswith("/"):
        r = "/" + r
    return base_url.rstrip("/") + r

def _extract_cards_from_inline_json(soup: BeautifulSoup, base_url: str) -> List["ReleaseCard"]:
    """
    Scan inline script tags for JSON blobs that contain product-ish objects and
    build ReleaseCard entries from them.
    """
    cards: list[ReleaseCard] = []
    seen_urls: set[str] = set()
    # Be liberal in what we accept
    script_tags = soup.find_all("script")
    for tag in script_tags:
        raw = tag.string or ""
        raw = raw.strip()
        if not raw:
            continue

        parsed = None
        # Quick sanity: only try to json.loads strings that look like JSON
        if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith("[") and raw.endswith("]")):
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None

        if parsed is None:
            # Fallback: look for small JSON fragments inside the JS by brute regex
            # This catches {"repositoryId":"100012345", ...} chunks embedded in larger scripts.
            for m in re.finditer(r'\{[^{}]*?"(?:product\.)?repositoryId"\s*:\s*"(.*?)"[^{}]*\}', raw, flags=re.DOTALL):
                try:
                    frag = json.loads(m.group(0))
                except Exception:
                    continue
                parsed = frag
                # Treat this fragment alone
                for d in _iter_dicts(parsed):
                    rid = _first_nonempty(
                        d.get("repositoryId"),
                        d.get("product.repositoryId"),
                        d.get("sku.repositoryId"),
                        d.get("product", {}).get("repositoryId") if isinstance(d.get("product"), dict) else None,
                        d.get("sku", {}).get("repositoryId") if isinstance(d.get("sku"), dict) else None,
                    )
                    if not rid:
                        continue

                    title = _first_nonempty(
                        d.get("displayName"),
                        d.get("product.displayName") if isinstance(d.get("product"), dict) else None,
                        d.get("sku.displayName") if isinstance(d.get("sku"), dict) else None,
                    ) or f"Product {rid}"

                    route = _first_nonempty(
                        d.get("route"),
                        d.get("seoUrl"),
                        d.get("seoUrlSlugDerived"),
                        d.get("product", {}).get("route") if isinstance(d.get("product"), dict) else None,
                        d.get("sku", {}).get("route") if isinstance(d.get("sku"), dict) else None,
                    )
                    url = _to_abs_route(route, base_url) or None

                    img = _first_nonempty(
                        d.get("primaryMediumImageURL"),
                        d.get("primaryLargeImageURL"),
                        d.get("primaryFullImageURL"),
                        d.get("sku.primaryMediumImageURL"),
                        d.get("sku.primaryLargeImageURL"),
                        d.get("sku.primaryFullImageURL"),
                    )
                    if img:
                        img = _normalize_image_url(img, base_url)

                    # Build key using URL if present, else repositoryId
                    key_src = (url or rid)
                    key = "release:" + _stable_key_from(key_src)

                    if url and url.lower() in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url.lower())

                    cards.append(ReleaseCard(
                        key=key,
                        title=title,
                        url=url or (base_url.rstrip("/") + "/"),
                        image_url=img,
                        status="",   # unknown from JSON; UI text will set later if needed
                    ))
            # Done with regex fallback for this tag
            continue

        # If we have parsed JSON (dict/list), walk it for product dicts
        for d in _iter_dicts(parsed):
            rid = _first_nonempty(
                d.get("repositoryId"),
                d.get("product.repositoryId"),
                d.get("sku.repositoryId"),
                d.get("product", {}).get("repositoryId") if isinstance(d.get("product"), dict) else None,
                d.get("sku", {}).get("repositoryId") if isinstance(d.get("sku"), dict) else None,
            )
            if not rid:
                continue

            title = _first_nonempty(
                d.get("displayName"),
                d.get("product.displayName") if isinstance(d.get("product"), dict) else None,
                d.get("sku.displayName") if isinstance(d.get("sku"), dict) else None,
            ) or f"Product {rid}"

            route = _first_nonempty(
                d.get("route"),
                d.get("seoUrl"),
                d.get("seoUrlSlugDerived"),
                d.get("product", {}).get("route") if isinstance(d.get("product"), dict) else None,
                d.get("sku", {}).get("route") if isinstance(d.get("sku"), dict) else None,
            )
            url = _to_abs_route(route, base_url) or None

            img = _first_nonempty(
                d.get("primaryMediumImageURL"),
                d.get("primaryLargeImageURL"),
                d.get("primaryFullImageURL"),
                d.get("sku.primaryMediumImageURL"),
                d.get("sku.primaryLargeImageURL"),
                d.get("sku.primaryFullImageURL"),
            )
            if img:
                img = _normalize_image_url(img, base_url)

            key_src = (url or rid)
            key = "release:" + _stable_key_from(key_src)

            if url and url.lower() in seen_urls:
                continue
            if url:
                seen_urls.add(url.lower())

            cards.append(ReleaseCard(
                key=key,
                title=title,
                url=url or (base_url.rstrip("/") + "/"),
                image_url=img,
                status="",
            ))

    return cards


def _parse_image_url(item: dict, base_url: str) -> str:
    rel = item.get("primaryMediumImageURL") or item.get("primaryLargeImageURL")
    if isinstance(rel, list):
        rel = rel[0] if rel else ""
    if rel:
        return _normalize_image_url(str(rel), base_url)
    return ""


def _parse_page_url(item: dict, base_url: str) -> str:
    """Resolve the product page URL."""
    route = (
        item.get("route")
        or item.get("seoUrl")
        or item.get("seoUrlSlugDerived")
        or item.get("relativeURL")
        or ""
    )
    if isinstance(route, list):
        route = route[0] if route else ""
    route = str(route or "")
    if not route:
        return base_url.rstrip("/")
    if route.startswith("http://") or route.startswith("https://"):
        return route
    if not route.startswith("/"):
        route = "/" + route
    return base_url.rstrip("/") + route

ONLINE_EXCLUSIVE_CATEGORY_IDS = {"3030473779"}  # Online Exclusives
# Extra hints used if category ids are missing (common on some tenants)
_ONLINE_EXCLUSIVE_ROUTE_HINTS = (
    "online-exclusive",
    "online_exclusive",
    "online-only",
    "onlineonly",
    "web-exclusive",
    "web_exclusive",
)

def _extract_category_ids_from_item(item: dict) -> set[str]:
    """
    Normalize category ids from various OCC/assembler shapes into a set of strings.
    Looks at:
      - categoryId (scalar or list)
      - category.repositoryId
      - parentCategories: [{repositoryId: ...}]
      - ancestorCategories: [{repositoryId: ...}]
      - categoryIds (our own helper field we may add upstream)
      - is_online_exclusive (short-circuit flag if caller already decided)
    """
    ids: set[str] = set()

    def _add(v):
        if v is None:
            return
        if isinstance(v, (list, tuple, set)):
            for x in v:
                _add(x)
            return
        s = str(v).strip()
        if s:
            ids.add(s)

    # direct
    _add(item.get("categoryId"))
    _add(item.get("categoryIds"))  # allow callers to stuff a list here

    # nested .category.repositoryId
    cat = item.get("category") or {}
    if isinstance(cat, dict):
        _add(cat.get("repositoryId"))

    # parentCategories / ancestorCategories arrays of dicts
    for key in ("parentCategories", "ancestorCategories"):
        arr = item.get(key)
        if isinstance(arr, list):
            for c in arr:
                if isinstance(c, dict):
                    _add(c.get("repositoryId"))

    return ids
def _extract_parent_categories(attrs: dict) -> list[dict]:
    """
    Pull parent/ancestor category dicts from assembler record attributes.
    We accept several possible shapes and normalize to [{'repositoryId': '...'}, ...].
    """
    out: list[dict] = []

    def _add_repo_id(x):
        if not x:
            return
        if isinstance(x, dict):
            rid = x.get("repositoryId") or x.get("id")
            if rid:
                out.append({"repositoryId": str(rid)})
        elif isinstance(x, (list, tuple)):
            for y in x:
                _add_repo_id(y)

    # Common shapes we’ve seen:
    for key in ("parentCategories", "ancestorCategories", "categories", "parentCategory"):
        val = attrs.get(key)
        if val is not None:
            _add_repo_id(val)

    # Some feeds provide just a single categoryId
    cat_id = attrs.get("categoryId")
    if isinstance(cat_id, list):
        for c in cat_id:
            if c:
                out.append({"repositoryId": str(c)})
    elif cat_id:
        out.append({"repositoryId": str(cat_id)})

    # Single nested category.* record:
    cat = attrs.get("category")
    if isinstance(cat, dict):
        rid = cat.get("repositoryId") or cat.get("id")
        if rid:
            out.append({"repositoryId": str(rid)})

    return out

def build_products(items: Iterable[dict], stock: Dict[str, int], base_url: str) -> List[Product]:
    products: List[Product] = []
    for item in items:
        pid = str(item.get("repositoryId") or "")
        if not pid:
            continue

        # If caller already marked it, honor that.
        if "is_online_exclusive" in item:
            is_oe = 1 if item.get("is_online_exclusive") else 0
        else:
            cat_ids = _extract_category_ids_from_item(item)
            by_cat = any(cid in ONLINE_EXCLUSIVE_CATEGORY_IDS for cid in cat_ids)

            # Fallback: infer from route (and, very conservatively, name)
            route_bits = " ".join(str(x or "") for x in (
                item.get("route"),
                item.get("seoUrl"),
                item.get("seoUrlSlugDerived"),
                item.get("relativeURL"),
            )).lower()
            by_route = any(h in route_bits for h in _ONLINE_EXCLUSIVE_ROUTE_HINTS)
            name_hit = "online exclusive" in str(item.get("displayName") or "").lower()

            is_oe = 1 if (by_cat or by_route or name_hit) else 0

        products.append(
            Product(
                id=pid,
                name=str(item.get("displayName", "")),
                price=_parse_price(item),
                image_url=_parse_image_url(item, base_url),
                page_url=_parse_page_url(item, base_url),
                quantity=int(stock.get(pid, 0)),
                is_online_exclusive=is_oe,
            )
        )
    return products




def fetch_stock_quantities(
    product_ids: Sequence[str],
    base_url: str = BASE_URL,
    session: Optional[requests.Session] = None,
    chunk_size: int = 50,
) -> Dict[str, int]:
    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    quantities: Dict[str, int] = {}
    url = _build_stock_status_endpoint(base_url)

    try:
        for i in range(0, len(product_ids), chunk_size):
            chunk = product_ids[i : i + chunk_size]
            params = {
                "products": ",".join(chunk),
                "expandStockDetails": "true",
                "actualStockStatus": "true",
                "locationIds": "null",
            }
            logger.debug("Fetching stock for %s items", len(chunk))
            resp = _get(session, url, params=params)
            data = resp.json()
            for itm in data.get("items", []):
                inv = itm.get("productSkuInventoryStatus") or {}
                for pid, qty in inv.items():
                    try:
                        quantities[pid] = int(qty)
                    except (ValueError, TypeError):
                        quantities[pid] = 0
    finally:
        if close_session:
            session.close()
    return quantities


# ---------------------------
# HTML enrichment utilities (price, quantity, image)
# ---------------------------

_HTML_PRICE_SELECTORS = [
    'span.card__price-amount',
    '[itemprop="price"]',
    '.price__value',
    '.cc-product-price__value',
    '.cc-pdp-price__value',
    'meta[itemprop="price"][content]',
]

# Prefer meta og:image first (often absolute CDN URL), then inline img.
_HTML_IMAGE_SELECTORS = [
    'meta[property="og:image"]',
    'meta[name="og:image"]',
    'link[rel="image_src"]',
    "img.card_image_id",
    "div.card__image img",
]

def _parse_price_number(text: str) -> float | None:
    if not text:
        return None
    t = str(text).strip()
    if re.fullmatch(r"\d+(\.\d+)?", t):
        try:
            return float(t)
        except ValueError:
            pass
    t = re.sub(r"[^0-9\.,]", "", t).replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _extract_price_from_jsonld(soup: BeautifulSoup) -> float | None:
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        blocks = data if isinstance(data, list) else [data]
        for b in blocks:
            offers = b.get("offers")
            if not offers:
                continue
            if isinstance(offers, list):
                for off in offers:
                    price = off.get("price") or off.get("priceSpecification", {}).get("price")
                    val = _parse_price_number(str(price)) if price is not None else None
                    if val:
                        return val
            elif isinstance(offers, dict):
                price = offers.get("price") or offers.get("priceSpecification", {}).get("price")
                val = _parse_price_number(str(price)) if price is not None else None
                if val:
                    return val
    return None


def _extract_price_from_html(soup: BeautifulSoup) -> float | None:
    val = _extract_price_from_jsonld(soup)
    if val:
        return val
    for sel in _HTML_PRICE_SELECTORS:
        el = soup.select_one(sel)
        if not el:
            continue
        if el.name and el.name.lower() == "meta":
            content = el.get("content")
            val = _parse_price_number(content or "")
            if val:
                return val
        txt = el.get_text(separator=" ", strip=True)
        val = _parse_price_number(txt)
        if val:
            return val
    m = re.search(r"\$\s*([0-9]+\.[0-9]{2})", soup.get_text(" ", strip=True))
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _extract_qty_from_html(soup: BeautifulSoup) -> int | None:
    el = soup.select_one("div.availability-info")
    if not el:
        return None
    txt = el.get_text(" ", strip=True)
    m = re.search(r"\b(\d+)\b", txt)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _extract_image_url_from_html(soup: BeautifulSoup, base_url: str) -> str | None:
    for sel in _HTML_IMAGE_SELECTORS:
        el = soup.select_one(sel)
        if not el:
            continue
        # meta/link provide content/href; img provides src
        src = el.get("content") or el.get("href") or el.get("src")
        if not src:
            continue
        return _normalize_image_url(src, base_url)
    return None

_BROWSER_UAS = [
    # A couple of realistic desktop Chrome UAs. Rotate to avoid simple blocks.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

def _browser_headers(base_url: str, alt: bool = False) -> dict:
    """
    Return realistic browser headers. `alt=True` switches UA and tweaks fetch hints.
    """
    ua = _BROWSER_UAS[1 if alt else 0]
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
        "Referer": base_url.rstrip("/") + "/",
    }

def _warm_up_site(session: requests.Session, base_url: str) -> None:
    """
    Hit the homepage to set any cookies (Akamai/edge) before fetching deep paths.
    Ignore failures; this is best-effort.
    """
    try:
        session.get(
            base_url.rstrip("/") + "/",
            headers=_browser_headers(base_url),
            timeout=12,
            allow_redirects=True,
        )
    except Exception:
        logger.debug("Warm-up request failed (non-fatal).", exc_info=True)

# --- replace your _fetch_html with this version ---

def _fetch_html(session: requests.Session, url: str) -> str | None:
    """
    Fetch HTML with browser-like headers and a homepage warm-up to dodge 403s.
    Uses direct session.get here (not the retry-decorated _get) to avoid
    5x retries on known 403s; we do a short local fallback sequence instead.
    """
    base = BASE_URL
    # 1) Warm up cookies (once per call; cheap)
    _warm_up_site(session, base)

    # Small cache-buster query to avoid overzealous edge caches
    cache_bust = f"{'&' if '?' in url else '?'}_={int(time.time()) % 100000}"
    url1 = url + cache_bust

    try_variants = [
        _browser_headers(base, alt=False),
        _browser_headers(base, alt=True),
    ]

    for idx, hdrs in enumerate(try_variants, start=1):
        try:
            resp = session.get(url1, headers=hdrs, timeout=14, allow_redirects=True)
            if resp.status_code == 200 and resp.text:
                return resp.text
            if resp.status_code in (301, 302, 303, 307, 308) and resp.text:
                return resp.text
            if resp.status_code == 403:
                logger.debug("Release HTML fetch attempt %d got 403; rotating headers.", idx)
                # Try a second cache-busted path if we got 403
                url1 = url + f"{'&' if '?' in url else '?'}_r={random.randint(10_000, 99_999)}"
                continue
            # Other non-200s: log at debug and bail
            logger.debug("HTML fetch non-200: %s for %s", resp.status_code, url)
        except Exception:
            logger.debug("HTML fetch error on attempt %d", idx, exc_info=True)

    # Give up quietly (caller will handle None)
    return None

def _fetch_html_browser(url: str, base_url: str = BASE_URL) -> str | None:
    """
    Render the page with headless Chromium and return HTML.
    Only used for the release page (expensive).
    """
    if not _PLAYWRIGHT_AVAILABLE:
        logger.info("Release: Playwright not available; set RELEASE_USE_BROWSER=false or install it (pip install playwright && python -m playwright install chromium).")
        return None

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError  # local import to avoid import errors at module load
        with sync_playwright() as p:
            logger.info("Release: using Playwright browser fallback for %s", url)
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                locale="en-US",
            )
            page = ctx.new_page()
            try:
                page.goto(base_url.rstrip("/") + "/", wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.goto(url, wait_until="networkidle", timeout=RELEASE_BROWSER_TIMEOUT_MS)
            html = page.content()
            ctx.close()
            browser.close()
            return html
    except PWTimeoutError:
        logger.info("Release: Playwright timeout loading %s", url)
        return None
    except Exception:
        logger.info("Release: Playwright failed for %s", url, exc_info=True)
        return None


def enrich_products_for_notifications(
    products: List[Product],
    *,
    delay_seconds: float = 0.6,
    base_url: str = BASE_URL,
) -> None:
    """
    For each product, fetch its product page and try to fill:
      - price (only if <= 0)
      - quantity (only if <= 0; API remains source of truth if > 0)
      - image_url (only if empty)
    """
    if not products:
        return

    session = get_http_session()
    try:
        for p in products:
            need_price = (p.price is None) or (float(p.price) <= 0.0)
            need_qty = (p.quantity is None) or (int(p.quantity) <= 0)
            need_img = not bool(p.image_url)

            if not (need_price or need_qty or need_img):
                continue

            html = _fetch_html(session, p.page_url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            if need_price:
                price = _extract_price_from_html(soup)
                if price is not None and price > 0:
                    p.price = price

            if need_qty:
                qty = _extract_qty_from_html(soup)
                if qty is not None and qty >= 0:
                    p.quantity = qty

            if need_img:
                img = _extract_image_url_from_html(soup, base_url=base_url)
                if img:
                    p.image_url = img

            if delay_seconds and delay_seconds > 0:
                time.sleep(delay_seconds)
    finally:
        session.close()

def fetch_all_product_items(
    category_id: str = CATEGORY_ID,
    base_url: str = BASE_URL,
    session: Optional[requests.Session] = None,
    force_legacy: bool = False,
) -> List[dict]:
    """Preferred: OSF assembler paging; Fallback: v1/products paging."""
    is_oe_context = category_id in ONLINE_EXCLUSIVE_CATEGORY_IDS
    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    try:
        # ---- Preferred: assembler paging ----
        if not force_legacy:
            assembler_url = (
                f"{base_url.rstrip('/')}/ccstore/v1/assembler/pages/Default/osf/catalog"
            )
            all_records: List[dict] = []
            offset = 0
            while True:
                params = {"N": category_id, "Nrpp": str(ASSEMBLER_NRPP), "No": str(offset)}
                if ASSEMBLER_NS:
                    params["Ns"] = ASSEMBLER_NS
                logger.debug("Assembler page fetch: %s %s", assembler_url, params)
                resp = _get(session, assembler_url, params=params)
                data = resp.json()
                results = data.get("results") or {}
                recs = (results.get("records") if isinstance(results, dict) else None) or data.get("records", [])
                if not isinstance(recs, list) or len(recs) == 0:
                    break
                all_records.extend(recs)
                offset += len(recs)

            if all_records:
                items = []
                for rec in all_records:
                    attrs = rec.get("attributes", rec)

                    def extract(names: Sequence[str]):
                        for name in names:
                            val = attrs.get(name)
                            if val is not None:
                                return val
                        return None

                    raw_id = extract(["repositoryId", "product.repositoryId", "sku.repositoryId"])
                    if raw_id is None:
                        continue
                    if isinstance(raw_id, list):
                        raw_id = raw_id[0]
                    repository_id = str(raw_id)

                    raw_name = extract(["displayName", "product.displayName", "sku.displayName"]) or ""
                    if isinstance(raw_name, list):
                        raw_name = raw_name[0]
                    display_name = str(raw_name)

                    raw_list = extract(["listPrice", "sku.listPrice"])
                    raw_sale = extract(["salePrice", "sku.salePrice"])
                    list_price = float(raw_list) if raw_list is not None else None
                    sale_price = float(raw_sale) if raw_sale is not None else None

                    raw_img = extract([
                        "primaryMediumImageURL",
                        "sku.primaryMediumImageURL",
                        "primaryLargeImageURL",
                        "sku.primaryLargeImageURL",
                        "sku.primaryFullImageURL",
                    ])
                    image_rel = raw_img[0] if isinstance(raw_img, list) else raw_img

                    raw_route = extract(["route", "product.route", "sku.route", "seoUrl", "seoUrlSlugDerived"])
                    route = raw_route[0] if isinstance(raw_route, list) else raw_route

                    parent_cats = _extract_parent_categories(attrs)
                    items.append({
                "repositoryId": repository_id,
                "displayName": display_name,
                "listPrice": list_price,
                "salePrice": sale_price,
                "primaryMediumImageURL": image_rel or None,
                "route": route or None,
                "parentCategories": parent_cats,
                "categoryIds": [c["repositoryId"] for c in parent_cats] if parent_cats else None,
                "is_online_exclusive": is_oe_context,  # <<<< HERE
            })

                return items

        # ---- Fallback: legacy v1/products paging ----
        products_url = f"{base_url.rstrip('/')}/ccstore/v1/products"
        offset = 0
        limit = 100
        all_items: List[dict] = []
        while True:
            params2 = {
                "categoryId": LEGACY_CATEGORY_ID,
                "limit": limit,
                "offset": offset,
            }
            logger.debug("Products fetch (legacy): offset=%s limit=%s", offset, limit)
            resp = _get(session, products_url, params=params2)
            data = resp.json()
            page_items = data.get("items", [])
            if not isinstance(page_items, list) or not page_items:
                break
            all_items.extend(page_items)
            total = int(data.get("totalResults", len(page_items)))
            offset += len(page_items)
            if offset >= total:
                break
        for it in all_items:
            it["is_online_exclusive"] = is_oe_context
        return all_items
    finally:
        if close_session:
            session.close()


def fetch_front_page_items(
    category_id: str = CATEGORY_ID,
    base_url: str = BASE_URL,
    nrpp: int = 120,
    ns_override: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> List[dict]:
    """Fetch the first assembler page (quick scan)."""
    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    try:
        assembler_url = f"{base_url.rstrip('/')}/ccstore/v1/assembler/pages/Default/osf/catalog"
        params = {"N": category_id, "Nrpp": str(nrpp), "No": "0"}
        use_ns = ns_override if ns_override is not None else ASSEMBLER_NS
        if use_ns:
            params["Ns"] = use_ns

        resp = _get(session, assembler_url, params=params)
        data = resp.json()

        results = data.get("results") or {}
        recs = (results.get("records") if isinstance(results, dict) else None) or data.get("records", [])

        items: List[dict] = []
        for rec in recs:
            attrs = rec.get("attributes", rec)

            def extract(names: Sequence[str]):
                for name in names:
                    val = attrs.get(name)
                    if val is not None:
                        return val
                return None

            raw_id = extract(["repositoryId", "product.repositoryId", "sku.repositoryId"])
            if raw_id is None:
                continue
            if isinstance(raw_id, list):
                raw_id = raw_id[0]
            repository_id = str(raw_id)

            raw_name = extract(["displayName", "product.displayName", "sku.displayName"]) or ""
            if isinstance(raw_name, list):
                raw_name = raw_name[0]
            display_name = str(raw_name)

            raw_list = extract(["listPrice", "sku.listPrice"])
            raw_sale = extract(["salePrice", "sku.salePrice"])
            list_price = float(raw_list) if raw_list is not None else None
            sale_price = float(raw_sale) if raw_sale is not None else None

            raw_img = extract([
                "primaryMediumImageURL",
                "sku.primaryMediumImageURL",
                "primaryLargeImageURL",
                "sku.primaryLargeImageURL",
                "sku.primaryFullImageURL",
            ])
            image_rel = raw_img[0] if isinstance(raw_img, list) else raw_img

            raw_route = extract(["route", "product.route", "sku.route", "seoUrlSlugDerived"])
            route = raw_route[0] if isinstance(raw_route, list) else raw_route

            parent_cats = _extract_parent_categories(attrs)
            items.append({
                "repositoryId": repository_id,
                "displayName": display_name,
                "listPrice": list_price,
                "salePrice": sale_price,
                "primaryMediumImageURL": image_rel or None,
                "route": route or None,
                # give build_products multiple options to detect OE
                "parentCategories": parent_cats,
                "categoryIds": [c["repositoryId"] for c in parent_cats] if parent_cats else None,
            })

        return items
    finally:
        if close_session:
            session.close()

# --- Coming Soon (HTML) ------------------------------------------------------

_COMING_SOON_NRPP = 12  # matches the site’s grid page size

def _extract_repo_id_from_href(href: str) -> Optional[str]:
    if not href:
        return None
    m = re.search(r"/product/(\d{6,})", href)
    return m.group(1) if m else None

def _product_card_container(a: Tag) -> Tag:
    # Walk up to a plausible tile/card element
    return a.find_parent(["li","article","div"]) or a

def _tile_has_coming_soon(card: Tag) -> bool:
    txt = card.get_text(" ", strip=True).lower()
    return "coming soon" in txt

def _tile_name(card: Tag, fallback_href: str) -> str:
    name_el = card.select_one("h2,h3,.card__name,.product__name,[itemprop='name']")
    if name_el:
        t = name_el.get_text(" ", strip=True)
        if t:
            return t
    # Try IMG alt
    img = card.find("img")
    if img and img.get("alt"):
        return img.get("alt").strip()
    # Fallback: last path segment or the href itself
    return fallback_href.rsplit("/", 1)[-1].replace("-", " ").strip() or "Coming Soon Item"

def _tile_price(card: Tag) -> Optional[float]:
    # try the common price spots on the grid
    el = card.select_one("span.card__price-amount,[itemprop='price'],.price__value,.cc-product-price__value")
    if not el:
        return None
    txt = el.get_text(" ", strip=True) if hasattr(el, "get_text") else str(el)
    txt = re.sub(r"[^0-9\.,]", "", txt).replace(",", "")
    try:
        return float(txt) if txt else None
    except ValueError:
        return None

def _tile_image(card: Tag, base_url: str) -> Optional[str]:
    # Prefer og:image if present higher up
    meta = card.select_one('meta[property="og:image"], meta[name="og:image"]')
    if meta and meta.get("content"):
        return _normalize_image_url(meta.get("content"), base_url)
    img = card.find("img")
    if img and img.get("src"):
        return _normalize_image_url(img.get("src"), base_url)
    return None

def _fetch_coming_soon_items_html(
    category_id: str = CATEGORY_ID,
    base_url: str = BASE_URL,
    session: Optional[requests.Session] = None,
    max_pages: int = 20,
) -> List[dict]:
    """
    Scrape the category listing HTML for tiles marked 'COMING SOON' and
    return items shaped like assembler/v1 products:
      { repositoryId, displayName, listPrice, salePrice, primaryMediumImageURL, route }
    """
    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    try:
        items: list[dict] = []
        seen: set[str] = set()
        # The site uses the /whiskey/151 route even while filtering by N=<categoryId>
        # That slug path renders the grid we can parse.
        base_path = f"{base_url.rstrip('/')}/whiskey/151"

        for page_idx in range(max_pages):
            params = {
                "N": category_id,
                "Ns": "B2CProduct.b2c_comingSoon|1",
                "Nrpp": str(_COMING_SOON_NRPP),
                "No": str(page_idx * _COMING_SOON_NRPP),
            }
            # Build the URL manually to avoid requests changing param order (not required, just tidy)
            from urllib.parse import urlencode
            url = f"{base_path}?{urlencode(params)}"

            html = _fetch_html(session, url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")
            anchors = soup.select('a[href*="/product/"]')
            found_this_page = 0

            for a in anchors:
                href = a.get("href") or ""
                rid = _extract_repo_id_from_href(href)
                if not rid:
                    continue
                card = _product_card_container(a)
                if not _tile_has_coming_soon(card):
                    continue  # only keep tiles explicitly marked "COMING SOON"

                if rid in seen:
                    continue
                seen.add(rid)
                found_this_page += 1

                name = _tile_name(card, href)
                price = _tile_price(card)
                img = _tile_image(card, base_url)
                route = href if href.startswith("http") else urljoin(base_url.rstrip("/") + "/", href.lstrip("/"))

                items.append({
                    "repositoryId": rid,
                    "displayName": name,
                    "listPrice": price,
                    "salePrice": None,
                    "primaryMediumImageURL": img,
                    "route": route,
                })

            # stop when a page returns no new "coming soon" cards
            if found_this_page == 0:
                break

        logger.info("ComingSoon HTML scan found %d items", len(items))
        return items
    finally:
        if close_session:
            session.close()


def _coerce_truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, list):
        return any(_coerce_truthy(x) for x in v)
    if isinstance(v, str):
        return v.strip().lower() in {"y", "yes", "true", "1"}
    return False

def _get_attr(attrs: dict, *names: str):
    """Return the first non-None attribute among possible names (handles list scalars)."""
    for name in names:
        val = attrs.get(name)
        if val is not None:
            if isinstance(val, list):
                return val[0] if val else None
            return val
    return None

def _is_coming_soon(attrs: dict) -> bool:
    # Try a handful of likely keys OCC exposes on the record
    candidates = (
        "B2CProduct.b2c_comingSoon",
        "b2c_comingSoon",
        "product.b2c_comingSoon",
        "sku.b2c_comingSoon",
        "B2CProduct.b2cComingSoon",
        "b2cComingSoon",
    )
    val = None
    for k in candidates:
        if k in attrs:
            val = _get_attr(attrs, k)
            break
    return _coerce_truthy(val)

def fetch_coming_soon_items(
    category_id: str = CATEGORY_ID,
    base_url: str = BASE_URL,
    session: Optional[requests.Session] = None,
    nrpp: int = ASSEMBLER_NRPP,
) -> List[dict]:
    """
    Preferred path: assembler paging, sorted by comingSoon, but *filtered* locally
    to only items that actually have the comingSoon flag set.

    Fallback: HTML grid scraper if assembler yields zero.
    """
    close_session = False
    if session is None:
        session = get_http_session()
        close_session = True

    try:
        assembler_url = f"{base_url.rstrip('/')}/ccstore/v1/assembler/pages/Default/osf/catalog"
        sort_expr = COMING_SOON_NS or "B2CProduct.b2c_comingSoon|1"

        out: List[dict] = []
        seen: set[str] = set()
        offset = 0

        while True:
            params = {"N": category_id, "Nrpp": str(nrpp), "No": str(offset), "Ns": sort_expr}
            logger.debug("ComingSoon assembler fetch: %s %s", assembler_url, params)
            resp = _get(session, assembler_url, params=params)
            data = resp.json()

            results = data.get("results") or {}
            recs = (results.get("records") if isinstance(results, dict) else None) or data.get("records", [])
            if not isinstance(recs, list) or not recs:
                break

            kept_this_page = 0
            for rec in recs:
                attrs = rec.get("attributes", rec)
                # FILTER: only keep records flagged as coming soon
                if not _is_coming_soon(attrs):
                    continue

                def extract(names: Sequence[str]):
                    v = _get_attr(attrs, *names)
                    return v

                raw_id = extract(["repositoryId", "product.repositoryId", "sku.repositoryId"])
                if raw_id is None:
                    continue
                repository_id = str(raw_id)

                if repository_id in seen:
                    continue
                seen.add(repository_id)

                raw_name = extract(["displayName", "product.displayName", "sku.displayName"]) or ""
                display_name = str(raw_name[0] if isinstance(raw_name, list) else raw_name)

                raw_list = extract(["listPrice", "sku.listPrice"])
                raw_sale = extract(["salePrice", "sku.salePrice"])
                list_price = float(raw_list) if raw_list is not None else None
                sale_price = float(raw_sale) if raw_sale is not None else None

                raw_img = extract([
                    "primaryMediumImageURL",
                    "sku.primaryMediumImageURL",
                    "primaryLargeImageURL",
                    "sku.primaryLargeImageURL",
                    "sku.primaryFullImageURL",
                ])
                image_rel = raw_img[0] if isinstance(raw_img, list) else raw_img

                raw_route = extract(["route", "product.route", "sku.route", "seoUrl", "seoUrlSlugDerived"])
                route = raw_route[0] if isinstance(raw_route, list) else raw_route

                out.append({
                    "repositoryId": repository_id,
                    "displayName": display_name,
                    "listPrice": list_price,
                    "salePrice": sale_price,
                    "primaryMediumImageURL": image_rel or None,
                    "route": route or None,
                })
                kept_this_page += 1

            offset += len(recs)

            # Optional optimization: once we hit a page with 0 kept while we keep paging through
            # a sort that has all the "coming soon" first, we *could* break. Safer to read all
            # pages—FWGS sometimes interleaves.
            # if kept_this_page == 0:
            #     break

        if out:
            logger.info("ComingSoon assembler scan kept %d items (from %d total records).", len(out), offset)
            return out

        # Fallback to HTML grid if assembler-postfilter yields zero
        logger.info("ComingSoon assembler-postfilter returned 0; falling back to HTML grid parse.")
        return _fetch_coming_soon_items_html(category_id=category_id, base_url=base_url, session=session)

    finally:
        if close_session:
            session.close()



__all__ = [
    "Product",
    "fetch_all_product_items",
    "fetch_stock_quantities",
    "build_products",
    "enrich_products_for_notifications",
    "fetch_front_page_items",
    "ReleaseCard",
    "fetch_release_cards",
    "fetch_coming_soon_items",
]

