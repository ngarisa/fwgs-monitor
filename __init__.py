"""
Product monitoring service package.

This package contains modules for scraping the Fine Wine & Good Spirits OCC
APIs, persisting seen products, notifying Discord and coordinating the
monitoring loop.  See README.md for details.
"""

__all__ = [
    "config",
    "db",
    "notifier",
    "scraper",
    "main",
    "utils",
]