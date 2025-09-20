"""Configuration loader.

Reads environment variables and `.env` to configure the service.
"""

from __future__ import annotations

import os, shutil
from typing import Optional, List
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a .env file if present (project root).
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def _get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes")


# ---- Core scraping config ----------------------------------------------------

# Primary/legacy single category (kept for backward compatibility).
# For Whiskey, FWGS uses Endeca node "4036262580".
CATEGORY_ID: str = _get_env("CATEGORY_ID", "4036262580")
# config.py
import os

ONLINE_EXCLUSIVE_CATEGORY_IDS = set(
    (os.getenv("ONLINE_EXCLUSIVE_CATEGORY_IDS") or "3030473779")
    .split(",")
)

# NEW: multiple Endeca category/node IDs to scrape in one pass.
# Comma-separated list. If unset, we fall back to [CATEGORY_ID].
_CATEGORY_IDS_RAW = _get_env("CATEGORY_IDS", "") or ""
CATEGORY_IDS: List[str] = [
    s.strip() for s in _CATEGORY_IDS_RAW.split(",") if s.strip()
]
if not CATEGORY_IDS:
    CATEGORY_IDS = [CATEGORY_ID]

# Interval in minutes between full catalog scrapes.
try:
    SCRAPE_INTERVAL_MINUTES: int = int(_get_env("SCRAPE_INTERVAL_MINUTES", "10"))
except ValueError:
    SCRAPE_INTERVAL_MINUTES = 10

# Discord webhook URL. Required for sending notifications.
DISCORD_WEBHOOK_URL: Optional[str] = _get_env("DISCORD_WEBHOOK_URL")

# Base URL for the OCC API. Should not include a trailing slash.
BASE_URL: str = _get_env("BASE_URL", "https://www.finewineandgoodspirits.com")

# Path to SQLite database.
SQLITE_DB_PATH: str = _get_env("SQLITE_DB_PATH", "monitor.db")

# Logging level: DEBUG, INFO, WARNING, ERROR.
LOG_LEVEL: str = _get_env("LOG_LEVEL", "INFO")

# OSF assembler page size request (server may cap).
try:
    ASSEMBLER_NRPP: int = int(_get_env("ASSEMBLER_NRPP", "2000"))
except ValueError:
    ASSEMBLER_NRPP = 2000

# Optional sort expression for assembler (Ns parameter). Leave blank for default.
ASSEMBLER_NS: Optional[str] = _get_env("ASSEMBLER_NS")

# Legacy v1/products fallback category slug.
LEGACY_CATEGORY_ID: str = _get_env("LEGACY_CATEGORY_ID", "151")

# ---- Feature flags & limits --------------------------------------------------

# Emit removed events for products that disappear from the catalog.
ENABLE_REMOVED_EVENTS: bool = _parse_bool(_get_env("ENABLE_REMOVED_EVENTS", "false"), False)

# Emit available events when quantity transitions from 0 -> >0.
ENABLE_STOCK_EVENTS: bool = _parse_bool(_get_env("ENABLE_STOCK_EVENTS", "true"), True)

# If > 0, cap the number of product notifications per cycle (ingestion is unaffected).
try:
    MAX_NOTIFY: int = int(_get_env("MAX_NOTIFY", "0"))
except ValueError:
    MAX_NOTIFY = 0

# ---- High-frequency watchlist loop ------------------------------------------

ENABLE_WATCHLIST: bool = _parse_bool(_get_env("ENABLE_WATCHLIST", "false"), False)

try:
    WATCHLIST_INTERVAL_SECONDS: int = int(_get_env("WATCHLIST_INTERVAL_SECONDS", "5"))
except ValueError:
    WATCHLIST_INTERVAL_SECONDS = 5

WATCHLIST_IDS_CSV: str = _get_env("WATCHLIST_IDS", "") or ""
WATCHLIST_IDS: List[str] = [s.strip() for s in WATCHLIST_IDS_CSV.split(",") if s.strip()]

# Optional simulator for local testing (forces a flip from 0→1 once).
SIMULATE_WATCHLIST_FLIP: bool = _parse_bool(_get_env("SIMULATE_WATCHLIST_FLIP", "false"), False)

# ---- Front-page scanner (optional) ------------------------------------------

ENABLE_FRONT_PAGE_SCANNER: bool = _parse_bool(_get_env("ENABLE_FRONT_PAGE_SCANNER", "false"), False)

try:
    FRONT_PAGE_NRPP: int = int(_get_env("FRONT_PAGE_NRPP", "120"))
except ValueError:
    FRONT_PAGE_NRPP = 120

# Optional sort expression specifically for "newest first" heuristic.
ASSEMBLER_NS_NEW: Optional[str] = _get_env("ASSEMBLER_NS_NEW")

# ---- Price/quantity enrichment (background) ---------------------------------

PRICE_FIXER_ENABLED: bool = _parse_bool(_get_env("PRICE_FIXER_ENABLED", "false"), False)

try:
    ENRICHMENT_BATCH_SIZE: int = int(_get_env("ENRICHMENT_BATCH_SIZE", "10"))
except ValueError:
    ENRICHMENT_BATCH_SIZE = 10

# Delay between per-product HTML requests (seconds)
try:
    ENRICHMENT_REQUEST_DELAY: float = float(_get_env("ENRICHMENT_REQUEST_DELAY", "1.5"))
except ValueError:
    ENRICHMENT_REQUEST_DELAY = 1.5

# Wait time between enrichment batches (seconds)
try:
    ENRICHMENT_LOOP_INTERVAL_SECONDS: int = int(_get_env("ENRICHMENT_LOOP_INTERVAL_SECONDS", "60"))
except ValueError:
    ENRICHMENT_LOOP_INTERVAL_SECONDS = 60

# Whether to upload images to Discord as attachments (most reliable).
DISCORD_ATTACH_IMAGES: bool = _parse_bool(_get_env("DISCORD_ATTACH_IMAGES", "false"))

# ---- Whiskey release browser fallback ---------------------------------------

def _parse_int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default

RELEASE_USE_BROWSER: bool = _parse_bool(_get_env("RELEASE_USE_BROWSER", "false"), False)
RELEASE_BROWSER_TIMEOUT_MS: int = _parse_int(_get_env("RELEASE_BROWSER_TIMEOUT_MS", "120000"), 120000)

ENABLE_RELEASE_SCANNER: bool = _parse_bool(_get_env("ENABLE_RELEASE_SCANNER", "false"), False)
RELEASE_PAGE_URL: Optional[str] = _get_env(
    "RELEASE_PAGE_URL",
    "https://www.finewineandgoodspirits.com/whiskey-release/whiskey-release",
)
RELEASE_CHECK_INTERVAL_SECONDS: int = _parse_int(_get_env("RELEASE_CHECK_INTERVAL_SECONDS", "15"), 15)

# ---- Validation --------------------------------------------------------------

def validate() -> None:
    """Validate required configuration parameters."""
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL must be set. See .env.example for details."
        )
# ---- Email notifications -----------------------------------------------------

def _get_list(name: str) -> list[str]:
    raw = _get_env(name, "") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]

EMAIL_ENABLED: bool = _parse_bool(_get_env("EMAIL_ENABLED", "false"), False)
EMAIL_SMTP_HOST: str = _get_env("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT: int = int(_get_env("EMAIL_SMTP_PORT", "587"))  # 587 (TLS) or 465 (SSL)
EMAIL_USE_TLS: bool = _parse_bool(_get_env("EMAIL_USE_TLS", "true"), True)  # if False and port=465, SSL will be used
EMAIL_USERNAME: str | None = _get_env("EMAIL_USERNAME")
EMAIL_PASSWORD: str | None = _get_env("EMAIL_PASSWORD")  # app password if using Gmail
EMAIL_FROM: str | None = _get_env("EMAIL_FROM")
EMAIL_TO: list[str] = _get_list("EMAIL_TO")  # comma-separated
EMAIL_SUBJECT_PREFIX: str = _get_env("EMAIL_SUBJECT_PREFIX", "[FWGS]")

# ---- auto checkout -----------------------------------------------------

AUTO_CHECKOUT_ENABLED = (os.getenv("AUTO_CHECKOUT_ENABLED","false").lower() == "true")
AUTO_CHECKOUT_EVENTS  = set(os.getenv("AUTO_CHECKOUT_EVENTS","available,new").split(","))
AUTO_CHECKOUT_DRY_RUN = (os.getenv("AUTO_CHECKOUT_DRY_RUN","true").lower() == "true")

# Keywords that trigger auto-checkout when found in product names (comma-separated)
AUTO_CHECKOUT_KEYWORDS_CSV: str = _get_env("AUTO_CHECKOUT_KEYWORDS", "") or ""
AUTO_CHECKOUT_KEYWORDS: List[str] = [s.strip().lower() for s in AUTO_CHECKOUT_KEYWORDS_CSV.split(",") if s.strip()]

# NEW: paths for the Node runner
# DIR = repo root, SCRIPT = path to the JS inside the package
AUTO_CHECKOUT_DIR    = os.getenv("AUTO_CHECKOUT_DIR", str(Path(__file__).resolve().parents[1]))
AUTO_CHECKOUT_SCRIPT = os.getenv("AUTO_CHECKOUT_SCRIPT", "product_monitor_service/generalized_checkout.js")
AUTO_CHECKOUT_NODE   = os.getenv("AUTO_CHECKOUT_NODE", shutil.which("node") or "node")

# Buyer info (only via env — don’t commit these)
CHECKOUT_FIRST_NAME = os.getenv("CHECKOUT_FIRST_NAME","")
CHECKOUT_LAST_NAME  = os.getenv("CHECKOUT_LAST_NAME","")
CHECKOUT_EMAIL      = os.getenv("CHECKOUT_EMAIL","")
CHECKOUT_PHONE      = os.getenv("CHECKOUT_PHONE","")
CHECKOUT_ADDRESS    = os.getenv("CHECKOUT_ADDRESS","")
CHECKOUT_CITY       = os.getenv("CHECKOUT_CITY","")
CHECKOUT_ZIP        = os.getenv("CHECKOUT_ZIP","")
CHECKOUT_CARDHOLDER_NAME = os.getenv("CHECKOUT_CARDHOLDER_NAME","")
CHECKOUT_CARD_NUMBER     = os.getenv("CHECKOUT_CARD_NUMBER","")
CHECKOUT_CVV             = os.getenv("CHECKOUT_CVV","")
CHECKOUT_EXPIRY          = os.getenv("CHECKOUT_EXPIRY","")
CHECKOUT_HEADLESS        = os.getenv("CHECKOUT_HEADLESS","true")

# ---- auto checkout -----------------------------------------------------

AUTO_CHECKOUT_ENABLED = (os.getenv("AUTO_CHECKOUT_ENABLED","false").lower() == "true")
AUTO_CHECKOUT_EVENTS  = set(os.getenv("AUTO_CHECKOUT_EVENTS","available,new").split(","))
AUTO_CHECKOUT_DRY_RUN = (os.getenv("AUTO_CHECKOUT_DRY_RUN","true").lower() == "true")

# NEW: keyword gating for auto-checkout
_AUTO_CHECKOUT_KEYWORDS_RAW = os.getenv("AUTO_CHECKOUT_KEYWORDS", "") or ""
AUTO_CHECKOUT_KEYWORDS: List[str] = [s.strip().lower() for s in _AUTO_CHECKOUT_KEYWORDS_RAW.split(",") if s.strip()]

# any = product matches at least one keyword, all = product must match every keyword
AUTO_CHECKOUT_MATCH_MODE = os.getenv("AUTO_CHECKOUT_MATCH_MODE", "any").strip().lower()  # "any" | "all"

# which fields to search for keywords (comma-separated: name,page_url,id)
_AUTO_CHECKOUT_SEARCH_FIELDS_RAW = os.getenv("AUTO_CHECKOUT_SEARCH_FIELDS", "name,page_url") or ""
AUTO_CHECKOUT_SEARCH_FIELDS: List[str] = [s.strip().lower() for s in _AUTO_CHECKOUT_SEARCH_FIELDS_RAW.split(",") if s.strip()]
_AUTO_INC = _get_env("AUTO_CHECKOUT_INCLUDE_KEYWORDS", "") or ""
_AUTO_EXC = _get_env("AUTO_CHECKOUT_EXCLUDE_KEYWORDS", "") or ""
AUTO_CHECKOUT_INCLUDE_KEYWORDS: list[str] = [s.strip().lower() for s in _AUTO_INC.split(",") if s.strip()]
AUTO_CHECKOUT_EXCLUDE_KEYWORDS: list[str] = [s.strip().lower() for s in _AUTO_EXC.split(",") if s.strip()]

try:
    AUTO_CHECKOUT_MIN_QTY: int = int(_get_env("AUTO_CHECKOUT_MIN_QTY", "1"))
except ValueError:
    AUTO_CHECKOUT_MIN_QTY = 1


__all__ = [
    # Core
    "CATEGORY_ID",
    "CATEGORY_IDS",
    "SCRAPE_INTERVAL_MINUTES",
    "DISCORD_WEBHOOK_URL",
    "BASE_URL",
    "SQLITE_DB_PATH",
    "LOG_LEVEL",
    "ASSEMBLER_NRPP",
    "ASSEMBLER_NS",
    "LEGACY_CATEGORY_ID",
    # Flags & limits
    "ENABLE_REMOVED_EVENTS",
    "ENABLE_STOCK_EVENTS",
    "MAX_NOTIFY",
    # Watchlist
    "ENABLE_WATCHLIST",
    "WATCHLIST_INTERVAL_SECONDS",
    "WATCHLIST_IDS",
    "SIMULATE_WATCHLIST_FLIP",
    # Front-page
    "ENABLE_FRONT_PAGE_SCANNER",
    "FRONT_PAGE_NRPP",
    "ASSEMBLER_NS_NEW",
    # Enrichment
    "PRICE_FIXER_ENABLED",
    "ENRICHMENT_BATCH_SIZE",
    "ENRICHMENT_REQUEST_DELAY",
    "ENRICHMENT_LOOP_INTERVAL_SECONDS",
    "DISCORD_ATTACH_IMAGES",
    # Release page scanner
    "ENABLE_RELEASE_SCANNER",
    "RELEASE_PAGE_URL",
    "RELEASE_CHECK_INTERVAL_SECONDS",
    "RELEASE_USE_BROWSER",
    "RELEASE_BROWSER_TIMEOUT_MS",
    # Helpers
    "validate",
    "EMAIL_ENABLED", "EMAIL_SMTP_HOST", "EMAIL_SMTP_PORT", "EMAIL_USE_TLS",
    "EMAIL_USERNAME", "EMAIL_PASSWORD", "EMAIL_FROM", "EMAIL_TO", "EMAIL_SUBJECT_PREFIX",
    # Auto checkout
    "AUTO_CHECKOUT_ENABLED", "AUTO_CHECKOUT_EVENTS", "AUTO_CHECKOUT_DRY_RUN", "AUTO_CHECKOUT_KEYWORDS",
    "AUTO_CHECKOUT_DIR", "AUTO_CHECKOUT_SCRIPT", "AUTO_CHECKOUT_NODE",
    "CHECKOUT_FIRST_NAME", "CHECKOUT_LAST_NAME", "CHECKOUT_EMAIL", "CHECKOUT_PHONE",
    "CHECKOUT_ADDRESS", "CHECKOUT_CITY", "CHECKOUT_ZIP", "CHECKOUT_CARDHOLDER_NAME",
    "CHECKOUT_CARD_NUMBER", "CHECKOUT_CVV", "CHECKOUT_EXPIRY", "CHECKOUT_HEADLESS",
    "AUTO_CHECKOUT_ENABLED",
    "AUTO_CHECKOUT_EVENTS",
    "AUTO_CHECKOUT_DRY_RUN",
    "AUTO_CHECKOUT_KEYWORDS",
    "AUTO_CHECKOUT_MATCH_MODE",
    "AUTO_CHECKOUT_SEARCH_FIELDS",
    "AUTO_CHECKOUT_DIR",
    "AUTO_CHECKOUT_SCRIPT",
    "AUTO_CHECKOUT_NODE",
]
