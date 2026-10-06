"""FastAPI wrapper over the CLI pipeline (PLAN.md §2.5).

    POST /analyze {"regulation_id": N, "version_no": N, "event_id": E?} -> analysis JSON
    GET  /health
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .analyze import AnalysisError, run_analysis

log = logging.getLogger(__name__)

app = FastAPI(
    title="regtrack-ai",
    version=__version__,
    description="LLM analysis, vector relevance and alert emission service.",
)


class AnalyzeRequest(BaseModel):
    regulation_id: int = Field(..., ge=1)
    version_no: int = Field(..., ge=1)
    event_id: int | None = None
    emit: bool = True


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ai", "version": __version__}


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    try:
        result = run_analysis(
            regulation_id=request.regulation_id,
            version_no=request.version_no,
            event_id=request.event_id,
            emit=request.emit,
        )
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface as 502 (backend/LLM infra)
        log.exception("analysis failed")
        raise HTTPException(
            status_code=502,
            detail=f"{type(exc).__name__}: {exc}") from exc
    return result.analysis
