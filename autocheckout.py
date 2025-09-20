from __future__ import annotations
import os, subprocess, threading, logging, time, re
from pathlib import Path
from . import config
from .scraper import Product

log = logging.getLogger(__name__)
_gate = threading.Semaphore(1)  # avoid running multiple checkouts at once

def _matches_keywords(product: Product) -> bool:
    hay = f"{(product.name or '').lower()} {product.page_url.lower()} {product.id}"
    if config.AUTO_CHECKOUT_EXCLUDE_KEYWORDS and any(kw in hay for kw in config.AUTO_CHECKOUT_EXCLUDE_KEYWORDS):
        return False
    if not config.AUTO_CHECKOUT_INCLUDE_KEYWORDS:
        return True
    return any(kw in hay for kw in config.AUTO_CHECKOUT_INCLUDE_KEYWORDS)


def _env_for_checkout(product_url: str) -> dict:
    env = os.environ.copy()
    env.update({
        "PRODUCT_URL": product_url,
        "CHECKOUT_FIRST_NAME": config.CHECKOUT_FIRST_NAME,
        "CHECKOUT_LAST_NAME":  config.CHECKOUT_LAST_NAME,
        "CHECKOUT_EMAIL":      config.CHECKOUT_EMAIL,
        "CHECKOUT_PHONE":      config.CHECKOUT_PHONE,
        "CHECKOUT_ADDRESS":    config.CHECKOUT_ADDRESS,
        "CHECKOUT_CITY":       config.CHECKOUT_CITY,
        "CHECKOUT_ZIP":        config.CHECKOUT_ZIP,
        "CHECKOUT_CARDHOLDER_NAME": config.CHECKOUT_CARDHOLDER_NAME,
        "CHECKOUT_CARD_NUMBER":     config.CHECKOUT_CARD_NUMBER,
        "CHECKOUT_CVV":             config.CHECKOUT_CVV,
        "CHECKOUT_EXPIRY":          config.CHECKOUT_EXPIRY,
        "CHECKOUT_HEADLESS":        config.CHECKOUT_HEADLESS,
    })
    return env

def _text_for_matching(product: Product) -> str:
    parts: list[str] = []
    fields = set(config.AUTO_CHECKOUT_SEARCH_FIELDS or [])
    if "name" in fields:
        parts.append(product.name or "")
    if "page_url" in fields:
        parts.append(product.page_url or "")
    if "id" in fields:
        parts.append(product.id or "")
    return " ".join(parts).lower()

def _matches_interest(product: Product) -> bool:
    kw = [k for k in (config.AUTO_CHECKOUT_KEYWORDS or []) if k]
    if not kw:
        # Back-compat: if no keywords configured, allow all
        return True
    hay = _text_for_matching(product)
    if config.AUTO_CHECKOUT_MATCH_MODE == "all":
        return all(k in hay for k in kw)
    return any(k in hay for k in kw)  # default "any"

def _should_attempt_auto(product: Product, event_type: str) -> bool:
    """Check if we should automatically checkout (keyword-based only)."""
    if not config.AUTO_CHECKOUT_ENABLED:
        return False
    if event_type not in config.AUTO_CHECKOUT_EVENTS:
        return False
    if product.quantity is not None and int(product.quantity) < int(config.AUTO_CHECKOUT_MIN_QTY):
        return False
    if product.price is not None and float(product.price) <= 0:
        return False
    # KEY CHANGE: Only auto-checkout if keywords match
    if not _matches_keywords(product):
        return False
    return True

def _should_attempt_manual(product: Product) -> bool:
    """Check if manual checkout is possible (less restrictive)."""
    if product.quantity is not None and int(product.quantity) < 1:
        return False
    if product.price is not None and float(product.price) <= 0:
        return False
    return True

def _analyze_checkout_output(output: str, stderr: str) -> tuple[bool, str]:
    """
    Analyze checkout script output to determine if it was successful.
    Returns (success, reason)
    """
    combined_output = f"{output}\n{stderr}".lower()
    
    # Check for success patterns
    success_patterns = getattr(config, 'AUTO_CHECKOUT_SUCCESS_PATTERNS', 'checkout completed,success: true').split(',')
    for pattern in success_patterns:
        if pattern.strip().lower() in combined_output:
            log.info("✅ Success pattern found: '%s'", pattern.strip())
            return True, f"Success: {pattern.strip()}"
    
    # Check for failure patterns
    failure_patterns = getattr(config, 'AUTO_CHECKOUT_FAILURE_PATTERNS', 'error,failed,timeout,declined').split(',')
    for pattern in failure_patterns:
        if pattern.strip().lower() in combined_output:
            log.warning("❌ Failure pattern found: '%s'", pattern.strip())
            return False, f"Failed: {pattern.strip()}"
    
    # If no clear success/failure pattern, check exit code behavior
    if "checkout completed" in combined_output:
        return True, "Checkout process completed"
    
    # Default to failure if we can't determine success
    return False, "Could not determine success/failure from output"

def _run_checkout_with_retry(product: Product, checkout_type: str = "AUTO") -> bool:
    """
    Run checkout with retry logic and output analysis.
    Returns True if successful, False otherwise.
    """
    max_retries = getattr(config, 'AUTO_CHECKOUT_MAX_RETRIES', 3)
    retry_delay = getattr(config, 'AUTO_CHECKOUT_RETRY_DELAY_SECONDS', 30)
    
    cmd = [config.AUTO_CHECKOUT_NODE, config.AUTO_CHECKOUT_SCRIPT, product.page_url]
    cwd = Path(config.AUTO_CHECKOUT_DIR)
    
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            if attempt > 0:
                log.info("🔄 Retry attempt %d/%d for %s (%s)", attempt, max_retries, product.name, product.id)
                time.sleep(retry_delay)
            else:
                log.info("🚀 Starting %s checkout for %s (%s)", checkout_type, product.name, product.id)
            
            env = _env_for_checkout(product.page_url)
            
            # Run with captured output for analysis
            p = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            log.info("🤖 Spawned %s checkout process pid=%s (attempt %d)", checkout_type, p.pid, attempt + 1)
            
            # Wait for completion and capture output
            stdout, stderr = p.communicate()
            rc = p.returncode
            
            # Also log the output in real-time style (for visibility)
            if stdout:
                for line in stdout.strip().split('\n'):
                    if line.strip():
                        log.info("CHECKOUT: %s", line.strip())
            
            if stderr:
                for line in stderr.strip().split('\n'):
                    if line.strip():
                        log.warning("CHECKOUT ERROR: %s", line.strip())
            
            # Analyze output for success/failure
            success, reason = _analyze_checkout_output(stdout, stderr)
            
            log.info("📊 %s checkout pid=%s exited rc=%s, analysis: %s", 
                    checkout_type, p.pid, rc, reason)
            
            if success:
                log.info("✅ %s checkout SUCCESSFUL for %s after %d attempts", 
                        checkout_type, product.name, attempt + 1)
                return True
            else:
                if attempt < max_retries:
                    log.warning("⚠️ %s checkout attempt %d FAILED for %s: %s (will retry in %ds)", 
                              checkout_type, attempt + 1, product.name, reason, retry_delay)
                else:
                    log.error("❌ %s checkout FAILED for %s after %d attempts: %s", 
                            checkout_type, product.name, max_retries + 1, reason)
                    return False
                    
        except Exception as e:
            if attempt < max_retries:
                log.exception("⚠️ %s checkout attempt %d crashed for %s (will retry in %ds)", 
                            checkout_type, attempt + 1, product.name, retry_delay)
            else:
                log.exception("❌ %s checkout crashed for %s after %d attempts", 
                            checkout_type, product.name, max_retries + 1)
                return False
    
    return False

def try_autocheckout(product: Product, event_type: str) -> None:
    """Automatically checkout predetermined keyword-based products only."""
    if not _should_attempt_auto(product, event_type):
        return

    if config.AUTO_CHECKOUT_DRY_RUN:
        log.info("[AUTO-CHECKOUT DRY RUN] Would run checkout for %s", product.name)
        return

    def _worker():
        with _gate:
            success = _run_checkout_with_retry(product, "AUTO")
            if success:
                log.info("🎉 AUTO checkout completed successfully for %s", product.name)
            else:
                log.error("💥 AUTO checkout failed permanently for %s", product.name)

    threading.Thread(target=_worker, name=f"auto_checkout_{product.id}", daemon=True).start()


def should_offer_manual_checkout(product: Product, event_type: str) -> bool:
    """Check if we should offer manual checkout option to user."""
    if not config.AUTO_CHECKOUT_ENABLED:
        return False
    # Don't offer manual checkout if this would auto-checkout anyway
    if _should_attempt_auto(product, event_type):
        return False
    # Only offer if the product is viable for checkout
    return _should_attempt_manual(product)


def try_manual_checkout(product: Product, force: bool = False) -> bool:
    """Manually trigger checkout for a specific product. Returns True if started."""
    if not force and not _should_attempt_manual(product):
        log.warning("Manual checkout declined for %s - product not viable", product.id)
        return False

    if config.AUTO_CHECKOUT_DRY_RUN:
        log.info("[MANUAL CHECKOUT DRY RUN] Would run checkout for %s", product.name)
        return True

    def _worker():
        with _gate:
            success = _run_checkout_with_retry(product, "MANUAL")
            if success:
                log.info("🎉 MANUAL checkout completed successfully for %s", product.name)
            else:
                log.error("💥 MANUAL checkout failed permanently for %s", product.name)

    threading.Thread(target=_worker, name=f"manual_checkout_{product.id}", daemon=True).start()
    return True