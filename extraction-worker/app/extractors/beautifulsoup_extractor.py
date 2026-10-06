"""
BeautifulSoup extractor – fast, lightweight HTML parsing for static pages.

Handles:
- Static government gazette pages
- Simple HTML tables (notification lists, circular indexes)
- Metadata extraction (title, gazette IDs, notification numbers)
- Document link discovery (PDFs, DOCXs)
"""

import re
import logging
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from app.models import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractedLink,
    ExtractedTable,
    PageMetadata,
)
from app.config import get_settings

logger = logging.getLogger(__name__)

# Document file extensions we care about
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".rtf", ".odt"}

# Government gazette metadata patterns
GAZETTE_ID_PATTERNS = [
    re.compile(r"gazette\s*(?:no|number|id)[.:\s]*([A-Z0-9\-/]+)", re.IGNORECASE),
    re.compile(r"notification\s*(?:no|number)[.:\s]*([A-Z0-9\-/().]+)", re.IGNORECASE),
    re.compile(r"circular\s*(?:no|number)[.:\s]*([A-Z0-9\-/().]+)", re.IGNORECASE),
    re.compile(r"order\s*(?:no|number)[.:\s]*([A-Z0-9\-/().]+)", re.IGNORECASE),
]

DATE_PATTERNS = [
    re.compile(r"dated?\s*[:\s]*(\d{1,2}[\s\-/.]\w+[\s\-/.]\d{2,4})", re.IGNORECASE),
    re.compile(r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})", re.IGNORECASE),
]


def extract_with_beautifulsoup(request: ExtractionRequest) -> ExtractionResponse:
    """Extract content from a URL using requests + BeautifulSoup."""
    settings = get_settings()
    start_time = time.time()

    try:
        # Fetch the page
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(
            request.url,
            headers=headers,
            timeout=settings.default_timeout,
            allow_redirects=True,
            verify=True,
        )
        resp.raise_for_status()
        raw_html = resp.text

        # Parse with BeautifulSoup
        soup = BeautifulSoup(raw_html, settings.bs4_parser)

        # Scope to a CSS selector if provided
        if request.css_selector:
            target = soup.select_one(request.css_selector)
            if target:
                soup = BeautifulSoup(str(target), settings.bs4_parser)

        # Extract metadata
        metadata = _extract_metadata(soup, raw_html) if request.include_metadata else PageMetadata()

        # Extract clean text
        clean_text = _extract_clean_text(soup)

        # Convert to markdown
        markdown = _html_to_markdown(soup)

        # Extract links
        links = []
        document_urls = []
        if request.include_links:
            links, document_urls = _extract_links(soup, request.url)

        # Extract tables
        tables = _extract_tables(soup) if request.include_tables else []

        elapsed_ms = int((time.time() - start_time) * 1000)

        return ExtractionResponse(
            url=request.url,
            strategy_used="beautifulsoup",
            success=True,
            raw_html=raw_html[:settings.max_content_length],
            clean_text=clean_text,
            markdown=markdown,
            metadata=metadata,
            links=links,
            tables=tables,
            document_urls=document_urls,
            content_length=len(clean_text),
            extraction_time_ms=elapsed_ms,
        )

    except requests.RequestException as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error("BeautifulSoup extraction failed for %s: %s", request.url, e)
        return ExtractionResponse(
            url=request.url,
            strategy_used="beautifulsoup",
            success=False,
            error=f"HTTP request failed: {str(e)}",
            extraction_time_ms=elapsed_ms,
        )
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error("BeautifulSoup extraction error for %s: %s", request.url, e, exc_info=True)
        return ExtractionResponse(
            url=request.url,
            strategy_used="beautifulsoup",
            success=False,
            error=f"Extraction error: {str(e)}",
            extraction_time_ms=elapsed_ms,
        )


def _extract_metadata(soup: BeautifulSoup, raw_html: str) -> PageMetadata:
    """Extract page metadata from HTML head and body content."""
    meta = PageMetadata()

    # Title
    title_tag = soup.find("title")
    if title_tag:
        meta.title = title_tag.get_text(strip=True)

    # Meta tags
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").lower()
        content = tag.get("content", "")
        if not content:
            continue
        if name in ("description", "og:description"):
            meta.description = content
        elif name in ("author", "article:author"):
            meta.author = content
        elif name in ("article:published_time", "date", "dc.date"):
            meta.published_date = content
        elif name in ("language", "dc.language"):
            meta.language = content

    # Language from html tag
    html_tag = soup.find("html")
    if html_tag and not meta.language:
        meta.language = html_tag.get("lang", "")

    # Gazette-specific metadata extraction from body text
    body_text = soup.get_text(" ", strip=True)

    for pattern in GAZETTE_ID_PATTERNS:
        match = pattern.search(body_text[:3000])  # Search early in the document
        if match:
            if "gazette" in pattern.pattern.lower():
                meta.gazette_id = match.group(1).strip()
            elif "notification" in pattern.pattern.lower():
                meta.notification_number = match.group(1).strip()
            elif "circular" in pattern.pattern.lower():
                meta.notification_number = match.group(1).strip()
            break

    if not meta.published_date:
        for pattern in DATE_PATTERNS:
            match = pattern.search(body_text[:3000])
            if match:
                meta.published_date = match.group(1).strip()
                break

    # Try to identify the issuing authority
    authority_keywords = [
        "Reserve Bank of India", "RBI",
        "Securities and Exchange Board", "SEBI",
        "Ministry of Corporate Affairs", "MCA",
        "Ministry of Finance",
        "Central Board of Direct Taxes", "CBDT",
        "Insurance Regulatory", "IRDAI",
        "Goods and Services Tax", "GST Council",
    ]
    for keyword in authority_keywords:
        if keyword.lower() in body_text[:2000].lower():
            meta.issuing_authority = keyword
            break

    return meta


def _extract_clean_text(soup: BeautifulSoup) -> str:
    """Extract clean readable text from HTML, removing scripts and styles."""
    # Remove unwanted elements
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        element.decompose()

    text = soup.get_text("\n", strip=True)

    # Collapse excessive whitespace/newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def _extract_links(soup: BeautifulSoup, base_url: str) -> tuple[list[ExtractedLink], list[str]]:
    """Extract all links and identify document URLs."""
    links = []
    document_urls = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue

        absolute_url = urljoin(base_url, href)
        text = a_tag.get_text(strip=True) or ""

        parsed = urlparse(absolute_url)
        path_lower = parsed.path.lower()
        is_doc = any(path_lower.endswith(ext) for ext in DOCUMENT_EXTENSIONS)

        links.append(ExtractedLink(text=text, href=absolute_url, is_document=is_doc))

        if is_doc:
            document_urls.append(absolute_url)

    return links, document_urls


def _extract_tables(soup: BeautifulSoup) -> list[ExtractedTable]:
    """Extract HTML tables as structured data."""
    tables = []

    for table_tag in soup.find_all("table"):
        caption_tag = table_tag.find("caption")
        caption = caption_tag.get_text(strip=True) if caption_tag else ""

        headers = []
        thead = table_tag.find("thead")
        if thead:
            for th in thead.find_all(["th", "td"]):
                headers.append(th.get_text(strip=True))
        else:
            # Use first row as headers if no thead
            first_row = table_tag.find("tr")
            if first_row:
                ths = first_row.find_all("th")
                if ths:
                    headers = [th.get_text(strip=True) for th in ths]

        rows = []
        tbody = table_tag.find("tbody") or table_tag
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row = [cell.get_text(strip=True) for cell in cells]
            # Skip the header row if it was already captured
            if row == headers:
                continue
            rows.append(row)

        if headers or rows:
            tables.append(ExtractedTable(headers=headers, rows=rows, caption=caption))

    return tables


def _html_to_markdown(soup: BeautifulSoup) -> str:
    """Convert HTML to a simple markdown representation."""
    # Remove unwanted elements
    for element in soup(["script", "style", "nav", "footer", "aside", "noscript"]):
        element.decompose()

    parts = []

    for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "pre", "blockquote"]):
        tag = element.name
        text = element.get_text(strip=True)
        if not text:
            continue

        if tag == "h1":
            parts.append(f"\n# {text}\n")
        elif tag == "h2":
            parts.append(f"\n## {text}\n")
        elif tag == "h3":
            parts.append(f"\n### {text}\n")
        elif tag in ("h4", "h5", "h6"):
            level = int(tag[1])
            parts.append(f"\n{'#' * level} {text}\n")
        elif tag == "p":
            parts.append(f"\n{text}\n")
        elif tag == "li":
            parts.append(f"- {text}")
        elif tag == "blockquote":
            parts.append(f"> {text}")
        elif tag == "pre":
            parts.append(f"\n```\n{text}\n```\n")

    result = "\n".join(parts)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
