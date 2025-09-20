"""SQLite persistence layer for product monitor service."""

from __future__ import annotations

import datetime as _dt
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping

from .config import SQLITE_DB_PATH
from .scraper import Product

def _get_connection() -> sqlite3.Connection:
    Path(SQLITE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db() -> None:
    """Create tables if they don't exist."""
    with _get_connection() as conn:
        conn.execute("""
          CREATE TABLE IF NOT EXISTS seen_products (
            repository_id TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL
          )
        """)
        conn.execute("""
          CREATE TABLE IF NOT EXISTS products (
            repository_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            image_url TEXT NOT NULL,
            page_url TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            removed INTEGER NOT NULL DEFAULT 0,
            available INTEGER NOT NULL DEFAULT 1,
            is_online_exclusive INTEGER NOT NULL DEFAULT 0
          )
        """)
        conn.execute("""
         CREATE TABLE IF NOT EXISTS watchlist (
           repository_id TEXT PRIMARY KEY,
           notes TEXT
         )
        """)
        conn.execute("""
         CREATE TABLE IF NOT EXISTS coming_soon (
           repository_id TEXT PRIMARY KEY,
           first_seen TEXT NOT NULL,
           last_seen  TEXT NOT NULL,
           active     INTEGER NOT NULL DEFAULT 1
         )
        """)

        # --- Migration guard for older DBs (idempotent) ---
        try:
            conn.execute("ALTER TABLE products ADD COLUMN is_online_exclusive INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists

        # Helpful index if you filter on OE
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_is_oe ON products(is_online_exclusive)")
        conn.commit()


def has_seen(product_id: str) -> bool:
    with _get_connection() as conn:
        cur = conn.execute(
            "SELECT 1 FROM seen_products WHERE repository_id = ? LIMIT 1",
            (product_id,),
        )
        return cur.fetchone() is not None

def mark_seen(product_ids: Iterable[str]) -> None:
    now = _dt.datetime.utcnow().isoformat()
    with _get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_products (repository_id, first_seen) VALUES (?, ?)",
            [(str(pid), now) for pid in product_ids],
        )
        conn.commit()

def get_all_products() -> Mapping[str, Product]:
    """Fetch all products from the DB, keyed by repository_id."""
    with _get_connection() as conn:
        cur = conn.execute("SELECT repository_id, name, price, image_url, page_url, quantity FROM products")
        result: dict[str, Product] = {}
        for row in cur.fetchall():
            pid, name, price, image_url, page_url, qty = row
            result[pid] = Product(
                id=pid,
                name=name,
                price=float(price),
                image_url=image_url,
                page_url=page_url,
                quantity=int(qty),
            )
        return result

def upsert_products(products: Iterable[Product]) -> None:
    """
    Insert new products or update existing ones.
    Updates last_seen, removed, available flags.
    IMPORTANT: Preserve existing non-zero price if incoming price <= 0.
    """
    now = _dt.datetime.utcnow().isoformat()

    rows = []
    for p in products:
        rows.append((
            str(p.id),
            str(p.name),
            float(p.price if p.price is not None else 0.0),
            str(p.image_url or ""),
            str(p.page_url or ""),
            int(p.quantity or 0),
            now,   # first_seen
            now,   # last_seen
            0,     # removed
            1,     # available
            int(getattr(p, "is_online_exclusive", 0)),
        ))

    with _get_connection() as conn:
        conn.executemany("""
            INSERT INTO products (
            repository_id, name, price, image_url, page_url,
            quantity, first_seen, last_seen, removed, available,
            is_online_exclusive
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id) DO UPDATE SET
            name       = excluded.name,
            image_url  = CASE
                            WHEN excluded.image_url IS NOT NULL AND excluded.image_url <> '' THEN excluded.image_url
                            ELSE products.image_url
                        END,
            page_url   = CASE
                            WHEN excluded.page_url  IS NOT NULL AND excluded.page_url  <> '' THEN excluded.page_url
                            ELSE products.page_url
                        END,
            quantity   = excluded.quantity,
            last_seen  = excluded.last_seen,
            removed    = excluded.removed,
            available  = excluded.available,
            is_online_exclusive = excluded.is_online_exclusive,
            price      = CASE
                            WHEN excluded.price IS NOT NULL AND excluded.price > 0
                            THEN excluded.price
                            ELSE products.price
                        END
        """, rows)
        conn.commit()



def mark_removed(product_ids: Iterable[str]) -> None:
    now = _dt.datetime.utcnow().isoformat()
    with _get_connection() as conn:
        conn.executemany("""
            UPDATE products
               SET removed = 1,
                   available = 0,
                   last_seen = ?
             WHERE repository_id = ?
        """, [(now, str(pid)) for pid in product_ids])
        conn.commit()

def add_to_watchlist(product_ids: Iterable[str], notes: str | None = None) -> None:
    with _get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO watchlist (repository_id, notes) VALUES (?, ?)",
            [(str(pid), notes or "") for pid in product_ids],
        )
        conn.commit()

def get_watchlist_ids() -> list[str]:
    with _get_connection() as conn:
        cur = conn.execute("SELECT repository_id FROM watchlist")
        return [r[0] for r in cur.fetchall()]

def get_candidates_for_enrichment(limit: int = 25) -> list[dict]:
    """
    Return rows that still need price enrichment (price is NULL or <= 0).
    Uses repository_id as the primary key.
    """
    with _get_connection() as conn:
        # Order by last_seen (present in your schema) to spread work fairly
        cur = conn.execute(
            """
            SELECT repository_id, name, price, quantity, page_url
            FROM products
            WHERE price IS NULL OR price <= 0
            ORDER BY last_seen ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            {
                "id": r[0],          # keep "id" key name for callers
                "name": r[1],
                "price": r[2],
                "quantity": r[3],
                "page_url": r[4],
            }
            for r in rows
        ]


def update_product_price_qty(
    product_id: str, *, price: float | None = None, quantity: int | None = None
) -> None:
    """
    Update price/quantity for a single product. Only sets fields provided (non-None).
    """
    sets, params = [], []
    if price is not None:
        sets.append("price = ?")
        params.append(float(price))
    if quantity is not None:
        sets.append("quantity = ?")
        params.append(int(quantity))
    if not sets:
        return

    sql = f"UPDATE products SET {', '.join(sets)} WHERE repository_id = ?"
    params.append(str(product_id))

    with _get_connection() as conn:
        conn.execute(sql, tuple(params))
        conn.commit()

def get_active_coming_soon_ids() -> list[str]:
    with _get_connection() as conn:
        cur = conn.execute("SELECT repository_id FROM coming_soon WHERE active = 1")
        return [r[0] for r in cur.fetchall()]

def mark_coming_soon(product_ids: Iterable[str], active: bool) -> None:
    now = _dt.datetime.utcnow().isoformat()
    with _get_connection() as conn:
        if active:
            rows = [(str(pid), now, now) for pid in product_ids]
            conn.executemany("""
                INSERT INTO coming_soon (repository_id, first_seen, last_seen, active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(repository_id) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    active=1
            """, rows)
        else:
            rows = [(now, str(pid)) for pid in product_ids]
            conn.executemany("""
                UPDATE coming_soon
                SET last_seen = ?, active = 0
                WHERE repository_id = ?
            """, rows)
        conn.commit()

__all__ = [
    "init_db",
    "has_seen",
    "mark_seen",
    "get_all_products",
    "upsert_products",
    "mark_removed",
    "add_to_watchlist",
    "get_watchlist_ids",
    "get_candidates_for_enrichment",
    "update_product_price_qty",
    "get_active_coming_soon_ids", 
    "mark_coming_soon",
]
