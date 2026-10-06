"""
Firecrawl extractor – headless browser rendering for JavaScript-heavy pages.

Handles:
- Dynamic government portals that require JS execution
- Anti-bot bypass
- Clean LLM-ready Markdown conversion
- Deep crawling and link following
"""

import logging
import time
from typing import Optional

from app.models import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractedLink,
    PageMetadata,
)
from app.config import get_settings

logger = logging.getLogger(__name__)


def is_firecrawl_available() -> bool:
    """Check if Firecrawl is configured and available."""
    settings = get_settings()
    return bool(settings.firecrawl_api_key)


def extract_with_firecrawl(request: ExtractionRequest) -> ExtractionResponse:
    """Extract content from a URL using Firecrawl's headless browser + LLM-ready Markdown."""
    settings = get_settings()
    start_time = time.time()

    if not settings.firecrawl_api_key:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return ExtractionResponse(
            url=request.url,
            strategy_used="firecrawl",
            success=False,
            error="Firecrawl API key not configured. Set EXTRACT_FIRECRAWL_API_KEY.",
            extraction_time_ms=elapsed_ms,
        )

    try:
        from firecrawl import FirecrawlApp

        app = FirecrawlApp(
            api_key=settings.firecrawl_api_key,
            api_url=settings.firecrawl_api_url,
        )

        # Build scrape parameters
        scrape_params = {
            "formats": ["markdown", "html"],
        }

        # Add wait_for if JS rendering is needed
        if request.wait_for_js:
            scrape_params["waitFor"] = 5000  # Wait 5s for JS to load

        logger.info("Firecrawl scraping %s with params: %s", request.url, scrape_params)

        result = app.scrape_url(request.url, params=scrape_params)

        # Extract content from Firecrawl response
        markdown = result.get("markdown", "")
        raw_html = result.get("html", "")
        fc_metadata = result.get("metadata", {})

        # Build metadata
        metadata = PageMetadata(
            title=fc_metadata.get("title", ""),
            description=fc_metadata.get("description", ""),
            language=fc_metadata.get("language", ""),
            published_date=fc_metadata.get("publishedTime", ""),
            author=fc_metadata.get("author", ""),
        )

        # Extract links from Firecrawl's links data
        links = []
        document_urls = []
        fc_links = result.get("links", [])
        if isinstance(fc_links, list):
            for link_url in fc_links:
                if isinstance(link_url, str):
                    is_doc = any(link_url.lower().endswith(ext) for ext in
                                [".pdf", ".doc", ".docx", ".xls", ".xlsx"])
                    links.append(ExtractedLink(text="", href=link_url, is_document=is_doc))
                    if is_doc:
                        document_urls.append(link_url)

        # Clean text from markdown (strip markdown formatting)
        clean_text = _markdown_to_plain(markdown)

        elapsed_ms = int((time.time() - start_time) * 1000)

        return ExtractionResponse(
            url=request.url,
            strategy_used="firecrawl",
            success=True,
            raw_html=raw_html[:settings.max_content_length],
            clean_text=clean_text,
            markdown=markdown,
            metadata=metadata,
            links=links,
            document_urls=document_urls,
            content_length=len(clean_text),
            extraction_time_ms=elapsed_ms,
        )

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error("Firecrawl extraction failed for %s: %s", request.url, e, exc_info=True)
        return ExtractionResponse(
            url=request.url,
            strategy_used="firecrawl",
            success=False,
            error=f"Firecrawl extraction failed: {str(e)}",
            extraction_time_ms=elapsed_ms,
        )


def _markdown_to_plain(markdown: str) -> str:
    """Strip markdown formatting to produce plain text."""
    import re
    text = markdown
    # Remove headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove links but keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove images
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Remove code blocks
    text = re.sub(r"```[^`]*```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
