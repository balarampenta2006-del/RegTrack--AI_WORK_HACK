"""End-to-end pipeline tests: outputs and manifest contract (PLAN.md §2.3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from docproc.exceptions import EmptyContentError
from docproc.fetch import fetch
from docproc.process import process

REQUIRED_MANIFEST_KEYS = {
    "regulation_id",
    "version_no",
    "source",
    "source_url",
    "method",
    "content_path",
    "content_sha256",
    "char_count",
    "ocr_used",
    "extracted_at",
    "pipeline_version",
}


def test_fetch_copies_local_file_into_raw(sample_pdf: Path, storage_root: Path) -> None:
    fetched = fetch(str(sample_pdf), raw_dir=storage_root / "raw", name_hint="reg7_v2")
    assert fetched.path.is_file()
    assert fetched.path.parent == storage_root / "raw"
    assert fetched.source_url == ""
    assert fetched.content_type == "application/pdf"
    assert fetched.path.read_bytes() == sample_pdf.read_bytes()
    assert fetched.path.name.startswith("reg7_v2_")


def test_fetch_missing_path_raises(tmp_path: Path, storage_root: Path) -> None:
    from docproc.exceptions import FetchError

    with pytest.raises(FetchError):
        fetch(str(tmp_path / "absent.pdf"), raw_dir=storage_root / "raw")


def test_process_writes_text_and_manifest(sample_pdf: Path, storage_root: Path) -> None:
    manifest = process(
        str(sample_pdf), regulation_id=7, version_no=2, source="RBI",
        storage_root=storage_root,
    )

    content_file = storage_root / "processed" / "7" / "v2.txt"
    assert content_file.is_file()
    text = content_file.read_text(encoding="utf-8")
    assert text.strip()
    assert "international" in text

    assert REQUIRED_MANIFEST_KEYS <= set(manifest.keys())
    assert manifest["regulation_id"] == 7
    assert manifest["version_no"] == 2
    assert manifest["source"] == "RBI"
    assert manifest["source_url"] == ""
    assert manifest["method"] in {"html", "pdf", "ocr"}
    assert manifest["method"] == "pdf"
    assert manifest["content_path"] == "storage/processed/7/v2.txt"
    assert manifest["content_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert manifest["char_count"] == len(text)
    assert manifest["ocr_used"] is False
    assert isinstance(manifest["ocr_used"], bool)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest["extracted_at"])
    assert manifest["pipeline_version"] == "1.0"

    saved = json.loads(
        (storage_root / "processed" / "7" / "manifest.json").read_text(encoding="utf-8")
    )
    assert saved == manifest
    assert (storage_root / "processed" / "7" / "v2.manifest.json").is_file()
    raw_files = list((storage_root / "raw").iterdir())
    assert len(raw_files) == 1


def test_process_html_document(sample_html: Path, storage_root: Path) -> None:
    manifest = process(
        str(sample_html), regulation_id=3, version_no=1, storage_root=storage_root
    )
    assert manifest["method"] == "html"
    assert manifest["char_count"] > 0
    content = (storage_root / "processed" / "3" / "v1.txt").read_text(encoding="utf-8")
    assert '"Circular"' in content
    assert "<p>" not in content
    assert "var x" not in content


def test_process_empty_content_raises_controlled_error(
    empty_pdf: Path, storage_root: Path
) -> None:
    if shutil_which() is not None:
        pytest.skip("tesseract installed; degraded path not applicable")
    with pytest.raises(EmptyContentError):
        process(str(empty_pdf), regulation_id=9, version_no=1, storage_root=storage_root)
    assert not (storage_root / "processed" / "9" / "v1.txt").exists()


def shutil_which() -> str | None:
    import shutil

    return shutil.which("tesseract")


def test_process_is_idempotent_for_same_input(sample_pdf: Path, storage_root: Path) -> None:
    first = process(str(sample_pdf), regulation_id=7, version_no=2, storage_root=storage_root)
    second = process(str(sample_pdf), regulation_id=7, version_no=2, storage_root=storage_root)
    assert first["content_sha256"] == second["content_sha256"]
    assert len(list((storage_root / "raw").iterdir())) == 1
