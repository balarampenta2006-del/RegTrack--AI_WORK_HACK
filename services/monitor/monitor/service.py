"""FastAPI thin wrapper over the monitor CLI (PLAN.md §2.5).

Endpoints (port 8101):

* ``GET  /health`` → ``{"status": "ok", ...}``
* ``POST /run``    → ``{"checked": n, "changed": [url, ...]}``
  Optional JSON body: ``{"dry_run": false, "sources": ["RBI"]}``.

Run with::

    uvicorn monitor.service:app --host 0.0.0.0 --port 8101
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .config import load_settings, load_sources
from .retriever import HAS_PLAYWRIGHT, firecrawl_available
from .runner import MonitorRunner

log = logging.getLogger("monitor.service")

app = FastAPI(
    title="regtrack-monitor",
    description="Government website change detection service (Phase 2).",
    version="1.0.0",
)


class RunRequest(BaseModel):
    """Optional body for ``POST /run``."""

    dry_run: bool = Field(default=False, description="Detect and sign without sending.")
    sources: list[str] | None = Field(default=None, description="Restrict to source codes.")


@lru_cache(maxsize=1)
def get_runner() -> MonitorRunner:
    """Build the process-wide runner from environment + sources.yaml."""
    settings = load_settings()
    sources = load_sources(settings.sources_path)
    return MonitorRunner(settings, sources)


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness probe with engine/config diagnostics."""
    settings = load_settings()
    return {
        "status": "ok",
        "service": "monitor",
        "api_base": settings.api_base,
        "storage_dir": str(settings.storage_dir),
        "engines": {
            "http": True,
            "playwright": HAS_PLAYWRIGHT,
            "firecrawl": firecrawl_available(),
        },
    }


@app.post("/run")
def run(request: RunRequest | None = None) -> dict[str, object]:
    """Run one full check cycle and return the PLAN.md §2.5 summary."""
    request = request or RunRequest()
    only = {code.upper() for code in request.sources} if request.sources else None
    summary = get_runner().run_once(dry_run=request.dry_run, only=only)
    return {"checked": summary.checked, "changed": list(summary.changed)}
