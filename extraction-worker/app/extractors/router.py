"""
Smart routing layer that picks the best extraction strategy for a given URL.

Routing logic:
- If strategy is explicitly set → use that.
- If the URL matches known JS-heavy government portals → use Firecrawl.
- If Firecrawl is configured and wait_for_js is set → use Firecrawl.
- Otherwise → use BeautifulSoup (faster, lighter).
- If BeautifulSoup fails (e.g., Cloudflare block) → fallback to Firecrawl.
"""

import logging
from urllib.parse import urlparse

from app.models import ExtractionRequest, ExtractionResponse, ExtractionStrategy
from app.extractors.beautifulsoup_extractor import extract_with_beautifulsoup
from app.extractors.firecrawl_extractor import extract_with_firecrawl, is_firecrawl_available

logger = logging.getLogger(__name__)

# Government portals known to require JavaScript rendering
JS_HEAVY_DOMAINS = {
    "egazette.gov.in",
    "egazette.nic.in",
    "mca.gov.in",
    "sebi.gov.in",
    "legislative.gov.in",
    "indiacode.nic.in",
    "dor.gov.in",
    "cbdt.gov.in",
    "cbic.gov.in",
    "dgft.gov.in",
    "fema.rbi.org.in",
}


def route_extraction(request: ExtractionRequest) -> ExtractionResponse:
    """
    Route an extraction request to the best strategy.

    Priority order:
    1. Explicit strategy → honour it directly.
    2. AUTO mode:
       a. If URL is known JS-heavy + Firecrawl available → Firecrawl
       b. If wait_for_js flag set + Firecrawl available → Firecrawl
       c. Otherwise → BeautifulSoup (with Firecrawl fallback on failure)
    """

    if request.strategy == ExtractionStrategy.FIRECRAWL:
        logger.info("Explicit strategy: Firecrawl for %s", request.url)
        return extract_with_firecrawl(request)

    if request.strategy == ExtractionStrategy.BEAUTIFULSOUP:
        logger.info("Explicit strategy: BeautifulSoup for %s", request.url)
        return extract_with_beautifulsoup(request)

    # AUTO mode
    domain = _extract_domain(request.url)
    firecrawl_available = is_firecrawl_available()

    # Check if this is a known JS-heavy domain
    if firecrawl_available and _is_js_heavy(domain):
        logger.info("AUTO → Firecrawl (JS-heavy domain: %s) for %s", domain, request.url)
        result = extract_with_firecrawl(request)
        if result.success:
            return result
        logger.warning("Firecrawl failed for %s, falling back to BeautifulSoup", request.url)

    # Check if JS rendering was explicitly requested
    if firecrawl_available and request.wait_for_js:
        logger.info("AUTO → Firecrawl (wait_for_js=True) for %s", request.url)
        result = extract_with_firecrawl(request)
        if result.success:
            return result
        logger.warning("Firecrawl failed for %s, falling back to BeautifulSoup", request.url)

    # Default: BeautifulSoup (fast path)
    logger.info("AUTO → BeautifulSoup for %s", request.url)
    result = extract_with_beautifulsoup(request)

    # Fallback to Firecrawl if BS4 failed and Firecrawl is available
    if not result.success and firecrawl_available:
        logger.warning("BeautifulSoup failed for %s, falling back to Firecrawl", request.url)
        return extract_with_firecrawl(request)

    return result


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL, stripping www."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return host.removeprefix("www.")
    except Exception:
        return ""


def _is_js_heavy(domain: str) -> bool:
    """Check if a domain is known to require JavaScript rendering."""
    if domain in JS_HEAVY_DOMAINS:
        return True
    # Also match subdomains
    for js_domain in JS_HEAVY_DOMAINS:
        if domain.endswith("." + js_domain):
            return True
    return False
