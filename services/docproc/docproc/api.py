"""FastAPI thin wrapper (PLAN.md §2.5): ``POST /process`` on port 8102."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .exceptions import DocprocError
from .extract import ocr_available
from .process import process

app = FastAPI(
    title="docproc",
    description="Document retrieval, extraction and cleaning service.",
    version="1.0",
)


class ProcessRequest(BaseModel):
    """Request body of ``POST /process``."""

    input: str = Field(..., min_length=1, description="Document URL or local path")
    regulation_id: int = Field(..., ge=0, description="Target regulation id")
    version_no: int = Field(..., ge=1, description="Target version number")
    source: str = Field(default="RBI", min_length=1, description="Source code")


@app.exception_handler(DocprocError)
async def _docproc_error_handler(request: Any, exc: DocprocError) -> JSONResponse:
    """Map handled pipeline errors to HTTP 422 with a readable detail."""
    return JSONResponse(
        status_code=422, content={"error": type(exc).__name__, "detail": str(exc)}
    )


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness probe plus OCR capability flag."""
    return {"status": "ok", "service": "docproc", "ocr_available": ocr_available()}


@app.post("/process")
def process_document(payload: ProcessRequest) -> dict[str, Any]:
    """Run the pipeline and return the manifest JSON (PLAN.md §2.3)."""
    return process(
        payload.input,
        payload.regulation_id,
        payload.version_no,
        payload.source,
    )


def run() -> None:
    """Serve the app on ``DOCPROC_PORT`` (default 8102)."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DOCPROC_PORT", "8102")))


if __name__ == "__main__":
    run()
