from __future__ import annotations

import logging
import threading
import time
from typing import List, Set

from . import config, db, notifier, scraper
from . import emailer  # NEW
from . import fast_checkout  # NEW (USED FOR MANUAL CHECKOUT PROCESS VIA NOTIF)

def setup_logging() -> None:
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

def scrape_once(category_id: str) -> None:
    """Perform one scrape-and-notify cycle for a single Endeca node (category)."""
    logger = logging.getLogger(__name__)
    logger.info("Starting scrape for category N=%s…", category_id)
    try:
        # 1) Fetch the FULL catalog via the OSF assembler endpoint (no in-stock filter).
        orig_ns = config.ASSEMBLER_NS
        config.ASSEMBLER_NS = None
        items = scraper.fetch_all_product_items(
            category_id=category_id,
            base_url=config.BASE_URL,
        )
        config.ASSEMBLER_NS = orig_ns

        total = len(items)
        logger.info("Fetched %d total products (full catalog) for N=%s", total, category_id)
        if total == 0:
            logger.warning("No items returned from the assembler endpoint for N=%s.", category_id)
            return

        # 2) Fetch stock quantities (out-of-stock → quantity=0)
        ids = [str(it["repositoryId"]) for it in items if it.get("repositoryId")]
        stock = scraper.fetch_stock_quantities(ids, base_url=config.BASE_URL)

        # 3) Build Product dataclasses
        products = scraper.build_products(items, stock, base_url=config.BASE_URL)

        # 4) Upsert ALL products into the DB
        logger.info("Upserting %d products into the database (N=%s)", len(products), category_id)
        prior_map = db.get_all_products()
        db.upsert_products(products)

        for p in products:
            prev = prior_map.get(p.id)
            if prev and (p.price is None or p.price <= 0):
                p.price = float(prev.price or 0.0)

        # 5) Detect new products
        prior_ids = set(prior_map.keys())
        new_products: List[scraper.Product] = [p for p in products if p.id not in prior_ids]

        # 6) Detect restocks
        restocked: List[scraper.Product] = []
        if config.ENABLE_STOCK_EVENTS:
            for p in products:
                prev = prior_map.get(p.id)
                if prev and prev.quantity == 0 and p.quantity > 0:
                    restocked.append(p)

        # Respect MAX_NOTIFY only for notifications (not ingestion)
        if config.MAX_NOTIFY > 0:
            new_products = new_products[: config.MAX_NOTIFY]
            restocked = restocked[: config.MAX_NOTIFY]

        # 6.5) Enrich price/qty for items we're about to notify on
        to_notify: List[scraper.Product] = []
        to_notify.extend(new_products)
        to_notify.extend(restocked)
        if to_notify:
            try:
                scraper.enrich_products_for_notifications(to_notify)
            except AttributeError:
                pass

        # 7) Send notifications
        if new_products:
            notifier.send_notifications(new_products, webhook_url=config.DISCORD_WEBHOOK_URL)
            if config.EMAIL_ENABLED:
                emailer.send_notifications(new_products)
            db.mark_seen([p.id for p in new_products])
            logger.info("Notified about %d new products for N=%s.", len(new_products), category_id)

        for p in restocked:
            notifier.send_product_event(
                p,
                event_type="available",
                webhook_url=config.DISCORD_WEBHOOK_URL,
            )
            # NEW: email too
            if config.EMAIL_ENABLED:
                emailer.send_product_event(p, event_type="available")

            logger.info("Notified restock for product %s (id=%s) N=%s", p.name, p.id, category_id)

        if not (new_products or restocked):
            logger.info("No product changes detected this cycle for N=%s.", category_id)

    except Exception:
        logger.exception("Unexpected error during scrape for N=%s.", category_id)

    if 'products' in locals() and products:
        logger.info("First 5 products this cycle (N=%s):", category_id)
        for p in products[:5]:
            logger.info("%s | $%.2f | qty=%d", p.name[:48], p.price, p.quantity)

def fast_watchlist_loop() -> None:
    """Poll watchlisted product IDs very frequently and notify on 0→>0 flips."""
    logger = logging.getLogger(__name__)
    if config.WATCHLIST_IDS:
        db.add_to_watchlist(config.WATCHLIST_IDS, notes="seeded from env")

    last_qty: dict[str, int] = {}
    logger.info("Starting high-frequency watchlist loop (interval=%ss)", config.WATCHLIST_INTERVAL_SECONDS)

    while True:
        try:
            watch_ids = db.get_watchlist_ids()
            if not watch_ids:
                time.sleep(config.WATCHLIST_INTERVAL_SECONDS)
                continue

            quantities = scraper.fetch_stock_quantities(watch_ids, base_url=config.BASE_URL)

            if config.SIMULATE_WATCHLIST_FLIP:
                for pid in list(quantities.keys()):
                    if last_qty.get(pid, 0) == 0:
                        quantities[pid] = 1

            for pid in watch_ids:
                q = int(quantities.get(pid, 0))
                prev = last_qty.get(pid, 0)
                if prev == 0 and q > 0:
                    prod_map = db.get_all_products()
                    p = prod_map.get(pid)
                    if not p:
                        p = scraper.Product(
                            id=pid, name=f"Product {pid}", price=0.0,
                            image_url="", page_url=config.BASE_URL, quantity=q
                        )
                    notifier.send_product_event(p, event_type="available", webhook_url=config.DISCORD_WEBHOOK_URL)
                    logger.info("Watchlist: %s is now available (qty=%d)", pid, q)
                last_qty[pid] = q

        except Exception:
            logger.exception("Error in fast_watchlist_loop")
        finally:
            time.sleep(config.WATCHLIST_INTERVAL_SECONDS)

def front_page_loop() -> None:
    """Poll only the first assembler page to detect brand-new products fast (uses first CATEGORY_ID)."""
    logger = logging.getLogger(__name__)
    seen: Set[str] = set(db.get_all_products().keys())
    # Use the first configured category for the fast scanner
    primary_category = (config.CATEGORY_IDS[0] if config.CATEGORY_IDS else config.CATEGORY_ID)
    ns = config.ASSEMBLER_NS_NEW if config.ASSEMBLER_NS_NEW is not None else config.ASSEMBLER_NS
    logger.info(
        "Starting front-page scanner for N=%s (nrpp=%d, ns=%s)",
        primary_category, config.FRONT_PAGE_NRPP, "custom" if ns else "default"
    )
    while True:
        try:
            items = scraper.fetch_front_page_items(
                category_id=primary_category,
                base_url=config.BASE_URL,
                nrpp=config.FRONT_PAGE_NRPP,
                ns_override=ns,
            )
            for it in items:
                pid = str(it.get("repositoryId") or "")
                if not pid:
                    continue
                if pid not in seen:
                    logger.info("Front page discovered new repositoryId=%s (before slow sweep)", pid)
                    stock = scraper.fetch_stock_quantities([pid], base_url=config.BASE_URL)
                    products = scraper.build_products([it], stock, base_url=config.BASE_URL)
                    if products:
                        db.upsert_products(products)
                        db.mark_seen([p.id for p in products])
                        scraper.enrich_products_for_notifications(products)
                        notifier.send_notifications(products, webhook_url=config.DISCORD_WEBHOOK_URL)
                    seen.add(pid)
        except Exception:
            logger.exception("Error in front_page_loop")
        finally:
            time.sleep(2)

def release_page_loop() -> None:
    """
    Poll the Whiskey Release landing page for new tiles and for tiles
    that turn 'live' (e.g., show 'Shop Now' / 'Add to Cart').
    Uses seen_products to remember notifications:
      - release:<hash>           -> card seen
      - release_live:<hash>      -> card went live (notified)
    """
    logger = logging.getLogger(__name__)
    if not (config.RELEASE_PAGE_URL and config.ENABLE_RELEASE_SCANNER):
        logger.info("Release scanner disabled or URL missing.")
        return

    logger.info(
        "Starting release scanner (interval=%ss) at %s",
        config.RELEASE_CHECK_INTERVAL_SECONDS,
        config.RELEASE_PAGE_URL,
    )

    while True:
        try:
            cards = scraper.fetch_release_cards(
                config.RELEASE_PAGE_URL,
                base_url=config.BASE_URL,
            )
            if not cards:
                logger.info("Release scanner: no cards (blocked/empty) at %s", config.RELEASE_PAGE_URL)
                time.sleep(max(5, int(config.RELEASE_CHECK_INTERVAL_SECONDS)))
                continue

            for c in cards:
                if not db.has_seen(c.key):
                    notifier.send_release_event(
                        c,
                        event_type="release",
                        webhook_url=config.DISCORD_WEBHOOK_URL,
                    )
                    db.mark_seen([c.key])

                if (c.status or "").lower() == "live":
                    live_key = f"release_live:{c.key}"
                    if not db.has_seen(live_key):
                        notifier.send_release_event(
                            c,
                            event_type="live",
                            webhook_url=config.DISCORD_WEBHOOK_URL,
                        )
                        db.mark_seen([live_key])

        except Exception:
            logger.exception("Error in release_page_loop")
        finally:
            time.sleep(max(3, int(config.RELEASE_CHECK_INTERVAL_SECONDS)))

def _slow_loop_wrapper() -> None:
    """Wrap the scrape_once() in the original sleep loop, iterating all CATEGORY_IDS."""
    logger = logging.getLogger(__name__)
    while True:
        for cid in config.CATEGORY_IDS:
            scrape_once(cid)
        logger.info(
            "Sleeping for %d minutes before next slow sweep over %d categories.",
            config.SCRAPE_INTERVAL_MINUTES, len(config.CATEGORY_IDS)
        )
        time.sleep(config.SCRAPE_INTERVAL_MINUTES * 60)

def enrichment_loop() -> None:
    """
    Background job: fix price==0 rows and verify quantity with API.
    Processes in small batches with rate-limited HTML fetch.
    """
    logger = logging.getLogger(__name__)
    logger.info(
        "Starting enrichment loop (batch=%d, delay=%.2fs, interval=%ds)",
        config.ENRICHMENT_BATCH_SIZE,
        config.ENRICHMENT_REQUEST_DELAY,
        config.ENRICHMENT_LOOP_INTERVAL_SECONDS,
    )
    while True:
        try:
            candidates = db.get_candidates_for_enrichment(limit=config.ENRICHMENT_BATCH_SIZE)
            if not candidates:
                time.sleep(config.ENRICHMENT_LOOP_INTERVAL_SECONDS)
                continue

            ids = [c["id"] for c in candidates]
            qty_map = scraper.fetch_stock_quantities(ids, base_url=config.BASE_URL)

            prods: List[scraper.Product] = []
            for c in candidates:
                q = int(qty_map.get(c["id"], c.get("quantity") or 0))
                prods.append(
                    scraper.Product(
                        id=c["id"],
                        name=c.get("name") or f"Product {c['id']}",
                        price=float(c.get("price") or 0.0),
                        image_url="",
                        page_url=c.get("page_url") or config.BASE_URL,
                        quantity=q,
                    )
                )

            try:
                scraper.enrich_products_for_notifications(
                    prods,
                    delay_seconds=config.ENRICHMENT_REQUEST_DELAY,
                )
            except AttributeError:
                pass

            for p in prods:
                db.update_product_price_qty(p.id, price=p.price, quantity=p.quantity)

            logger.info("Enrichment: updated %d products", len(prods))

        except Exception:
            logger.exception("Error in enrichment_loop")

        time.sleep(config.ENRICHMENT_LOOP_INTERVAL_SECONDS)

def main() -> None:
    """Initialise and run the monitoring loops."""
    config.validate()
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("Initializing database…")
    db.init_db()

    # Start fast checkout server for instant manual checkouts
    logger.info("Starting fast checkout server…")
    fast_checkout_url = fast_checkout.start_server()
    if fast_checkout_url:
        logger.info("✅ Fast checkout server ready at %s", fast_checkout_url)
    else:
        logger.warning("⚠️ Fast checkout server failed to start - manual checkout will use CLI only")

    logger.info(
        "Starting product monitor for categories %s with slow interval %s minutes.",
        ", ".join(config.CATEGORY_IDS),
        config.SCRAPE_INTERVAL_MINUTES,
    )

    # Slow, thorough sweep over all configured Endeca nodes
    t_slow = threading.Thread(target=_slow_loop_wrapper, name="slow-sweep", daemon=True)
    t_slow.start()

    # Enrichment / price-fixer
    if config.PRICE_FIXER_ENABLED:
        t_enrich = threading.Thread(target=enrichment_loop, name="enrichment", daemon=True)
        t_enrich.start()
    else:
        logger.info("Price enrichment disabled.")

    # Fast watchlist loop
    if config.ENABLE_WATCHLIST:
        t_fast = threading.Thread(target=fast_watchlist_loop, name="fast-watchlist", daemon=True)
        t_fast.start()
    else:
        logger.info("Watchlist disabled.")

    # Optional front-page loop (uses first category)
    if config.ENABLE_FRONT_PAGE_SCANNER:
        t_front = threading.Thread(target=front_page_loop, name="front-page", daemon=True)
        t_front.start()
    else:
        logger.info("Front-page scanner disabled.")
        
    # Optional release page scanner
    if config.ENABLE_RELEASE_SCANNER:
        t_release = threading.Thread(target=release_page_loop, name="release-page", daemon=True)
        t_release.start()
    else:
        logger.info("Release scanner disabled.")

    t_slow.join()

if __name__ == "__main__":
    main()
