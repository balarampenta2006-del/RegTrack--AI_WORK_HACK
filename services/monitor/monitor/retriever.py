"""Retrieval layer: fetch a watch URL and reduce it to title + clean text.

Primary engine is ``httpx`` (falling back to ``requests``) plus BeautifulSoup
for extraction.  Two optional engines are guarded so the service degrades
gracefully when they are unavailable in the shared venv:

* ``playwright`` — guarded import; falls back to ``http`` with a warning.
* ``firecrawl`` — requires ``FIRECRAWL_API_KEY``; uses the SDK when it is
  importable, otherwise calls the REST API with ``httpx``; falls back to
  ``http`` with a warning when no key is configured.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is pre-installed
    httpx = None  # type: ignore[assignment]

try:
    import requests
except ImportError:  # pragma: no cover - requests is pre-installed
    requests = None  # type: ignore[assignment]

try:  # pragma: no cover - playwright is intentionally NOT installed
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except Exception:
    sync_playwright = None  # type: ignore[assignment]
    HAS_PLAYWRIGHT = False

try:  # pragma: no cover - firecrawl SDK is intentionally NOT installed
    from firecrawl import FirecrawlApp

    HAS_FIRECRAWL_SDK = True
except Exception:
    FirecrawlApp = None  # type: ignore[assignment]
    HAS_FIRECRAWL_SDK = False

log = logging.getLogger("monitor.retriever")

DEFAULT_USER_AGENT = "Mozilla/5.0"
_MAX_ATTEMPTS = 3
_WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
_FILE_SCHEME = "file://"


class FetchError(RuntimeError):
    """Raised when a watch URL cannot be retrieved or parsed."""


@dataclass(frozen=True)
class FetchResult:
    """Raw + parsed result of one retrieval."""

    url: str
    engine: str
    html: str
    text: str
    title: str
    fetched_at: str
    status_code: int | None = None


def utc_now_iso() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SSZ`` (webhook timestamp format)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_text(html: str) -> tuple[str, str]:
    """Extract ``(title, clean_text)`` from an HTML document.

    Script/style/svg blocks are dropped, remaining text is whitespace-normalised
    and blank lines removed so sha256 comparison stays stable.

    Args:
        html: Raw HTML document.

    Returns:
        Tuple of page title ("" when absent) and newline separated clean text.
    """
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    lines: list[str] = []
    for raw_line in soup.get_text(separator="\n").splitlines():
        line = _WHITESPACE_RE.sub(" ", raw_line).strip()
        if line:
            lines.append(line)
    return title, "\n".join(lines)


def firecrawl_available() -> bool:
    """True when the ``firecrawl`` engine can be attempted (key is set)."""
    return bool(os.environ.get("FIRECRAWL_API_KEY", "").strip())


def resolve_engine(engine: str) -> str:
    """Degrade an unavailable optional engine to ``http`` with a warning.

    Args:
        engine: Requested engine name.

    Returns:
        The engine that will actually be used.
    """
    if engine == "playwright" and not HAS_PLAYWRIGHT:
        log.warning("playwright engine requested but not installed; falling back to http")
        return "http"
    if engine == "firecrawl" and not firecrawl_available():
        log.warning("firecrawl engine requested but FIRECRAWL_API_KEY unset; falling back to http")
        return "http"
    return engine


def fetch(
    url: str,
    *,
    engine: str = "http",
    timeout: float = 30.0,
    user_agent: str = DEFAULT_USER_AGENT,
) -> FetchResult:
    """Retrieve ``url`` with the requested engine and parse title/text.

    Args:
        url: Watch URL (``http(s)://`` or ``file://``).
        engine: One of ``http``/``playwright``/``firecrawl``/``file``;
            unavailable optional engines degrade to ``http``.
        timeout: Per-request timeout in seconds.
        user_agent: User-Agent header for HTTP(S) requests.

    Returns:
        :class:`FetchResult` with raw HTML plus extracted title and text.

    Raises:
        FetchError: When every applicable engine fails.
    """
    engine = resolve_engine(engine)
    try:
        if url.startswith(_FILE_SCHEME):
            engine = "file"
            html, status = _fetch_file(url), None
        elif engine == "playwright":
            html, status = _fetch_playwright(url, timeout, user_agent)
        elif engine == "firecrawl":
            html, status = _fetch_firecrawl(url, timeout, user_agent)
        else:
            html, status = _fetch_http(url, timeout, user_agent)
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"fetch failed for {url}: {exc}") from exc

    title, text = extract_text(html)
    return FetchResult(
        url=url,
        engine=engine,
        html=html,
        text=text,
        title=title,
        fetched_at=utc_now_iso(),
        status_code=status,
    )


def _fetch_file(url: str) -> str:
    """Read a ``file://`` URL from disk (offline fixtures and dry runs)."""
    parsed = urlparse(url)
    path_str = unquote(parsed.path)
    if parsed.netloc:
        path_str = f"//{parsed.netloc}{path_str}"
    if re.match(r"^/[A-Za-z]:", path_str):
        path_str = path_str[1:]
    path = Path(path_str)
    if not path.exists():
        raise FetchError(f"local file not found: {path}")
    return path.read_text(encoding="utf-8")


def _fetch_http(url: str, timeout: float, user_agent: str) -> tuple[str, int]:
    """GET ``url`` with httpx (primary) or requests (fallback).

    Transient failures (connection errors, HTTP 429/5xx) are retried up to
    three times with linear backoff; other 4xx responses fail immediately.
    """
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            if httpx is not None:
                with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
                    response = client.get(url)
            elif requests is not None:
                response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            else:  # pragma: no cover - both are pre-installed
                raise FetchError("neither httpx nor requests is available")
            if response.status_code == 429 or response.status_code >= 500:
                raise RuntimeError(f"HTTP {response.status_code} from {url}")
            response.raise_for_status()
            return response.text, response.status_code
        except FetchError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_ATTEMPTS:
                log.info("attempt %d/%d for %s failed (%s); retrying", attempt, _MAX_ATTEMPTS, url, exc)
                time.sleep(0.5 * attempt)
    raise FetchError(f"fetch failed after {_MAX_ATTEMPTS} attempts for {url}: {last_error}")


def _fetch_playwright(url: str, timeout: float, user_agent: str) -> tuple[str, int]:
    """Headless-browser fetch for JavaScript-rendered pages (optional)."""
    if sync_playwright is None:  # pragma: no cover - guarded above
        raise FetchError("playwright is not installed")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=user_agent)
            response = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            return page.content(), response.status if response else None
        finally:
            browser.close()


def _fetch_firecrawl(url: str, timeout: float, user_agent: str) -> tuple[str, int]:
    """Firecrawl scrape (SDK when importable, otherwise REST via httpx)."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise FetchError("FIRECRAWL_API_KEY is not set")
    base_url = os.environ.get("FIRECRAWL_API_URL", "https://api.firecrawl.dev").rstrip("/")

    if HAS_FIRECRAWL_SDK and FirecrawlApp is not None:  # pragma: no cover - SDK absent
        try:
            app = FirecrawlApp(api_key=api_key, api_url=base_url)
            try:
                scraped = app.scrape(url, formats=["html"])
            except TypeError:
                scraped = app.scrape(url, params={"formats": ["html"]})
            html = ((scraped or {}).get("data") or {}).get("html")
            if html:
                return html, None
            log.warning("firecrawl SDK returned no html; retrying via REST")
        except Exception as exc:
            log.warning("firecrawl SDK failed (%s); retrying via REST", exc)

    if httpx is None:  # pragma: no cover - httpx is pre-installed
        raise FetchError("httpx is required for the firecrawl REST engine")
    response = httpx.post(
        f"{base_url}/v1/scrape",
        json={"url": url, "formats": ["html"]},
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": user_agent},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    html = ((payload or {}).get("data") or {}).get("html")
    if not html:
        raise FetchError(f"firecrawl returned no html for {url}")
    return html, None
