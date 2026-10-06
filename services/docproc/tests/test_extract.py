"""Extraction tests: PDF, HTML, plain text and graceful OCR fallback."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from docproc.clean import clean_text
from docproc.exceptions import EmptyContentError, ExtractionError, UnsupportedFormatError
from docproc.extract import extract, ocr_available


def test_extract_pdf_produces_text(sample_pdf: Path) -> None:
    result = extract(sample_pdf)
    assert result.method == "pdf"
    assert result.ocr_used is False
    assert result.note is None
    assert result.pages == 3
    assert "Master Direction Notice 1" in result.text
    assert "The inter-" in result.text
    assert "\f" in result.text


def test_extract_pdf_then_clean(sample_pdf: Path) -> None:
    cleaned = clean_text(extract(sample_pdf).text)
    assert cleaned.strip()
    assert "international" in cleaned
    assert "inter-\nnational" not in cleaned
    assert "Reserve Bank of India" not in cleaned
    assert "Page 1 of 3" not in cleaned
    assert "The international norm applies - firmly." in cleaned
    assert "Para two of notice 1 keeps a double space." in cleaned
    assert "  double" not in cleaned


def test_extract_html(sample_html: Path) -> None:
    result = extract(sample_html)
    assert result.method == "html"
    assert result.ocr_used is False
    assert "RBI" in result.text
    assert "var x" not in result.text
    assert "color: red" not in result.text
    cleaned = clean_text(result.text)
    assert '"Circular"' in cleaned
    assert "First paragraph" in cleaned
    assert "Trailing block" in cleaned
    assert "—" not in cleaned and "rule - applied nationwide" in cleaned
    assert "smart" in cleaned and "a space." in cleaned


def test_extract_plain_text(sample_text: Path) -> None:
    result = extract(sample_text)
    assert result.method == "html"
    assert "two lines" in result.text


def test_extract_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError):
        extract(tmp_path / "nope.pdf")


def test_extract_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")
    with pytest.raises(ExtractionError):
        extract(path)


def test_extract_unsupported_binary(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    path.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(UnsupportedFormatError):
        extract(path)


@pytest.mark.skipif(
    shutil.which("tesseract") is not None,
    reason="tesseract installed; degraded OCR path not applicable",
)
def test_ocr_fallback_when_tesseract_absent(empty_pdf: Path) -> None:
    assert ocr_available() is False
    start = time.perf_counter()
    result = extract(empty_pdf)
    elapsed = time.perf_counter() - start
    assert elapsed < 10, "OCR degradation must not hang"
    assert result.method == "ocr"
    assert result.ocr_used is False
    assert result.note is not None
    assert "tesseract" in result.note.lower()
    with pytest.raises(EmptyContentError) as excinfo:
        from docproc.process import process

        process(
            str(empty_pdf),
            regulation_id=8,
            version_no=1,
            storage_root=empty_pdf.parent / "storage",
        )
    assert "ocr" in str(excinfo.value).lower()


def test_ocr_flag_is_boolean_for_normal_pdf(sample_pdf: Path) -> None:
    result = extract(sample_pdf)
    assert isinstance(result.ocr_used, bool)


@pytest.mark.skipif(
    shutil.which("tesseract") is not None,
    reason="tesseract installed; degraded OCR path not applicable",
)
def test_image_input_ocr_fallback(tmp_path: Path) -> None:
    from PIL import Image

    image_path = tmp_path / "scan.png"
    Image.new("RGB", (200, 60), "white").save(image_path)
    result = extract(image_path)
    assert result.method == "ocr"
    assert result.ocr_used is False
    assert result.note is not None and "tesseract" in result.note.lower()
