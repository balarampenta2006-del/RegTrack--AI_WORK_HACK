"""Pipeline orchestrator: fetch -> extract -> clean -> manifest (PLAN.md §2.3)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .clean import clean_text
from .exceptions import EmptyContentError
from .extract import extract
from .fetch import fetch

PIPELINE_VERSION = "1.0"


def utc_now_iso() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_manifest(
    *,
    regulation_id: int,
    version_no: int,
    source: str,
    source_url: str,
    method: str,
    content_path: str,
    content_sha256: str,
    char_count: int,
    ocr_used: bool,
    extracted_at: str,
    note: str | None,
) -> dict[str, Any]:
    """Build the manifest dict consumed by the ai role (PLAN.md §2.3).

    ``note`` is the only field beyond §2.3; it records OCR/degradation
    situations and is ``null`` when nothing exceptional happened.
    """
    return {
        "regulation_id": regulation_id,
        "version_no": version_no,
        "source": source,
        "source_url": source_url,
        "method": method,
        "content_path": content_path,
        "content_sha256": content_sha256,
        "char_count": char_count,
        "ocr_used": ocr_used,
        "extracted_at": extracted_at,
        "pipeline_version": PIPELINE_VERSION,
        "note": note,
    }


def process(
    input_spec: str,
    regulation_id: int,
    version_no: int,
    source: str = "RBI",
    *,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run the full document-processing pipeline for one regulation version.

    Writes ``storage/raw/<hint>_<hash>_<name>`` (original),
    ``storage/processed/<id>/v<n>.txt`` (cleaned text),
    ``storage/processed/<id>/manifest.json`` and the version-pinned copy
    ``storage/processed/<id>/v<n>.manifest.json``.

    Args:
        input_spec: URL or local path of the source document.
        regulation_id: Target regulation id.
        version_no: Target version number (1-based).
        source: Source code, e.g. ``RBI``.
        storage_root: Overrides ``STORAGE_ROOT``/auto-detected storage root.

    Returns:
        The manifest dict exactly as written to disk.

    Raises:
        FetchError: Retrieval failure.
        ExtractionError/UnsupportedFormatError: Parsing failure.
        EmptyContentError: No usable text after extraction and cleaning.
    """
    root = Path(storage_root).expanduser() if storage_root else paths.storage_root()
    fetched = fetch(
        input_spec,
        raw_dir=paths.raw_dir(root),
        name_hint=f"reg{regulation_id}_v{version_no}",
    )
    result = extract(fetched.path, content_type=fetched.content_type)
    cleaned = clean_text(result.text)
    if not cleaned.strip():
        detail = f" ({result.note})" if result.note else ""
        raise EmptyContentError(
            f"no text could be extracted from {fetched.path.name} "
            f"using method '{result.method}'{detail}"
        )

    out_dir = paths.processed_dir(root, regulation_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    content_path = paths.content_file(root, regulation_id, version_no)
    content_path.write_text(cleaned, encoding="utf-8")

    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    manifest = build_manifest(
        regulation_id=regulation_id,
        version_no=version_no,
        source=source,
        source_url=fetched.source_url,
        method=result.method,
        content_path=paths.content_path_str(root, regulation_id, version_no),
        content_sha256=digest,
        char_count=len(cleaned),
        ocr_used=result.ocr_used,
        extracted_at=utc_now_iso(),
        note=result.note,
    )
    payload = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    (out_dir / "manifest.json").write_text(payload, encoding="utf-8")
    (out_dir / f"v{version_no}.manifest.json").write_text(payload, encoding="utf-8")
    return manifest
