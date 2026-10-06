"""Pydantic models for extraction request/response payloads."""

from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl
from enum import Enum
from typing import Optional


class ExtractionStrategy(str, Enum):
    """Which extraction engine to use."""
    AUTO = "auto"
    FIRECRAWL = "firecrawl"
    BEAUTIFULSOUP = "beautifulsoup"


class ExtractionRequest(BaseModel):
    """Request payload to extract content from a URL."""
    url: str = Field(..., description="The URL to extract content from")
    strategy: ExtractionStrategy = Field(
        default=ExtractionStrategy.AUTO,
        description="Extraction strategy: auto (smart routing), firecrawl, or beautifulsoup"
    )
    include_links: bool = Field(default=True, description="Whether to extract links")
    include_tables: bool = Field(default=True, description="Whether to extract tables")
    include_metadata: bool = Field(default=True, description="Whether to extract page metadata")
    css_selector: Optional[str] = Field(default=None, description="Optional CSS selector to scope extraction")
    wait_for_js: bool = Field(default=False, description="Force JS rendering (uses Firecrawl)")


class ExtractedLink(BaseModel):
    """A link extracted from the page."""
    text: str = ""
    href: str = ""
    is_document: bool = False  # True if it links to a PDF/DOC/etc.


class ExtractedTable(BaseModel):
    """A table extracted from the page."""
    headers: list[str] = []
    rows: list[list[str]] = []
    caption: str = ""


class PageMetadata(BaseModel):
    """Metadata extracted from the page."""
    title: str = ""
    description: str = ""
    published_date: str = ""
    author: str = ""
    language: str = ""
    gazette_id: str = ""
    notification_number: str = ""
    issuing_authority: str = ""
    extra: dict = Field(default_factory=dict)


class ExtractionResponse(BaseModel):
    """Response payload with extracted content."""
    url: str
    strategy_used: str
    success: bool = True
    error: Optional[str] = None

    # Content in multiple formats
    raw_html: str = ""
    clean_text: str = ""
    markdown: str = ""

    # Structured data
    metadata: PageMetadata = Field(default_factory=PageMetadata)
    links: list[ExtractedLink] = []
    tables: list[ExtractedTable] = []
    document_urls: list[str] = []  # PDF/DOCX links found on the page

    # Stats
    content_length: int = 0
    extraction_time_ms: int = 0


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "UP"
    service: str = "extraction-worker"
    firecrawl_configured: bool = False
