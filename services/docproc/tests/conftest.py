"""Shared fixtures: sys.path bootstrap, sample documents, storage root."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    (root / "raw").mkdir(parents=True, exist_ok=True)
    return root


def build_sample_pdf(path: Path) -> Path:
    """Create a 3-page PDF with a repeated header, page footers and EOL hyphenation."""
    import pymupdf

    doc = pymupdf.open()
    try:
        for index in range(3):
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 60), "Reserve Bank of India", fontsize=10)
            page.insert_text((72, 100), f"Master Direction Notice {index + 1}", fontsize=14)
            page.insert_text((72, 130), "The inter-", fontsize=11)
            page.insert_text((72, 145), "national norm applies - firmly.", fontsize=11)
            page.insert_text((72, 170), f"Para two of notice {index + 1} keeps a  double space.", fontsize=11)
            page.insert_text((72, 780), f"Page {index + 1} of 3", fontsize=10)
        doc.save(str(path))
    finally:
        doc.close()
    return path


def build_textless_pdf(path: Path) -> Path:
    """Create a PDF with no text layer (simulates a scanned document)."""
    import pymupdf

    doc = pymupdf.open()
    try:
        doc.new_page(width=595, height=842)
        doc.new_page(width=595, height=842)
        doc.save(str(path))
    finally:
        doc.close()
    return path


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    return build_sample_pdf(tmp_path / "sample.pdf")


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    return build_textless_pdf(tmp_path / "scanned.pdf")


@pytest.fixture
def sample_html(tmp_path: Path) -> Path:
    html = """<!doctype html>
<html><head><title>Gazette</title><script>var x = "ignored";</script>
<style>.a { color: red }</style></head>
<body><h1>RBI \u201cCircular\u201d 2026</h1>
<p>First paragraph with \u201csmart\u201d quotes and a\u00a0space.</p>
<p>Second paragraph continues the rule \u2014 applied nationwide.</p>
<br><div>Trailing block</div></body></html>"""
    path = tmp_path / "gazette.html"
    path.write_text(html, encoding="utf-8")
    return path


@pytest.fixture
def sample_text(tmp_path: Path) -> Path:
    path = tmp_path / "note.txt"
    path.write_text("Plain text input\nwith two lines.\n", encoding="utf-8")
    return path
