"""Helper utilities.

This module centralises common helper functions such as creating a
configured HTTP session and applying retry policies to network calls.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

import requests
from requests import Response
from tenacity import (after_log, retry, retry_if_exception_type,
                      stop_after_attempt, wait_exponential)


logger = logging.getLogger(__name__)


def get_http_session() -> requests.Session:
    """Return a new HTTP session with sensible defaults.

    The session sets a realistic User‑Agent header and disables
    SSL verification only when necessary.  Caller is responsible for
    closing the session or letting it be garbage collected.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; ProductMonitor/1.0; +https://github.com/)",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
    )
    # Respect environment proxies if configured (requests does this by default)
    return session


class HTTPError(Exception):
    """Raised when an HTTP request fails after retries."""


def _raise_for_status(resp: Response) -> None:
    try:
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPError(str(e)) from e


def retryable_request(method: Callable[[requests.Session, str, Dict[str, Any]], Response]) -> Callable[..., Response]:
    """Decorator factory to apply retry logic to HTTP calls.

    The decorated function must accept a `requests.Session` as its first
    argument, followed by URL and optional kwargs, and return a
    `requests.Response`.  Retries are attempted for network errors or
    HTTP errors (status >= 500).  A maximum of 5 attempts are made with
    exponential back‑off between 1 and 10 seconds.
    """

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=(
            retry_if_exception_type(requests.RequestException)
            | retry_if_exception_type(HTTPError)
        ),
        after=after_log(logger, logging.WARNING),
    )
    def wrapper(session: requests.Session, url: str, **kwargs: Any) -> Response:
        response = method(session, url, **kwargs)
        # If server returned >= 500, raise to trigger retry
        if response.status_code >= 500:
            raise HTTPError(f"Server returned status {response.status_code}")
        _raise_for_status(response)
        return response

    return wrapper


__all__ = ["get_http_session", "retryable_request", "HTTPError"]