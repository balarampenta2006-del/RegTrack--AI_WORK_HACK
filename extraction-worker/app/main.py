"""
RegTrack Extraction Worker – FastAPI service for web content extraction.

Provides two extraction engines:
1. BeautifulSoup – fast, lightweight HTML parsing for static pages
2. Firecrawl – headless browser rendering for JavaScript-heavy portals

The /extract endpoint accepts a URL and returns clean text, markdown,
structured metadata, links, tables, and document URLs (PDFs/DOCs).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.models import ExtractionRequest, ExtractionResponse, HealthResponse
from app.extractors.router import route_extraction
from app.extractors.firecrawl_extractor import is_firecrawl_available

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
    )
    logger.info("Extraction worker starting — service=%s", settings.service_name)
    logger.info("Firecrawl configured: %s", is_firecrawl_available())
    yield
    logger.info("Extraction worker shutting down")


app = FastAPI(
    title="RegTrack Extraction Worker",
    description="Web content extraction service using BeautifulSoup + Firecrawl",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="UP",
        service="extraction-worker",
        firecrawl_configured=is_firecrawl_available(),
    )


@app.post("/extract", response_model=ExtractionResponse)
async def extract(request: ExtractionRequest):
    """
    Extract content from a URL.

    Automatically routes to the best extraction strategy (BeautifulSoup or Firecrawl)
    based on the target domain and configuration. Can be overridden with the `strategy` field.

    Returns clean text, markdown, metadata, links, tables, and document URLs.
    """
    logger.info("Extraction request: url=%s strategy=%s", request.url, request.strategy)

    try:
        result = route_extraction(request)
    except Exception as e:
        logger.error("Extraction failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

    if not result.success:
        logger.warning("Extraction unsuccessful for %s: %s", request.url, result.error)

    return result


@app.post("/extract/batch", response_model=list[ExtractionResponse])
async def extract_batch(requests: list[ExtractionRequest]):
    """
    Extract content from multiple URLs in a single request.
    Each URL is processed sequentially.
    """
    if len(requests) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 URLs per batch request")

    results = []
    for req in requests:
        logger.info("Batch extraction: url=%s strategy=%s", req.url, req.strategy)
        try:
            result = route_extraction(req)
        except Exception as e:
            logger.error("Batch extraction failed for %s: %s", req.url, e)
            result = ExtractionResponse(
                url=req.url,
                strategy_used="error",
                success=False,
                error=str(e),
            )
        results.append(result)

    return results
