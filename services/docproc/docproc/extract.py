"""Text extraction from PDF, HTML and image documents.

OCR (pytesseract + Pillow) runs only when the tesseract binary is on PATH
(``shutil.which("tesseract")``); otherwise the OCR path degrades gracefully and
records why in :attr:`ExtractionResult.note`.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .exceptions import ExtractionError, UnsupportedFormatError

Method = Literal["html", "pdf", "ocr"]
Kind = Literal["pdf", "html", "image", "text"]

MIN_CHARS_PER_PAGE = 50
OCR_DPI = 200
OCR_TIMEOUT_S = 30

_DROP_TAGS = ("script", "style", "noscript", "template", "svg", "iframe")
_BLOCK_TAGS = (
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "table", "section", "article", "header", "footer", "blockquote",
    "pre", "hr", "dd", "dt", "figure", "figcaption", "nav", "aside",
)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of the extraction stage.

    Attributes:
        text: Extracted text, pages separated by form-feed (``\\f``).
        method: Pipeline used — ``html``, ``pdf`` or ``ocr``.
        ocr_used: True only when OCR actually produced text.
        note: Situation recorder (e.g. why OCR was skipped); ``None`` if fine.
        pages: Number of pages processed (1 for non-PDF inputs).
    """

    text: str
    method: Method
    ocr_used: bool
    note: str | None
    pages: int


def ocr_available() -> bool:
    """Return True when the tesseract binary and the Python OCR stack are usable."""
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:
        return False
    return True


def _magic_kind(head: bytes) -> Kind | None:
    if head[:5] == b"%PDF-":
        return "pdf"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if head[:3] == b"\xff\xd8\xff":
        return "image"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    return None


def _kind_for(path: Path, data: bytes, content_type: str | None) -> Kind:
    magic = _magic_kind(data[:16])
    if magic:
        return magic
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct == "application/pdf" or ct.endswith("/pdf"):
        return "pdf"
    if ct.startswith("image/"):
        return "image"
    if ct in {"text/html", "application/xhtml+xml"}:
        return "html"
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in {".txt", ".md"}:
        return "text"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnsupportedFormatError(
            f"unsupported or undecodable document format for {path.name}"
        ) from None
    head = data[:512].lstrip().lower()
    if head.startswith(b"<") or b"<html" in head:
        return "html"
    return "text"


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _html_to_text(data: bytes) -> str:
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(data, "lxml")
    except Exception:
        soup = BeautifulSoup(data, "html.parser")
    for tag in soup.find_all(list(_DROP_TAGS)):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(list(_BLOCK_TAGS)):
        tag.insert_before("\n")
        tag.insert_after("\n")
    return soup.get_text()


def _ocr_image(path: Path) -> tuple[str, str | None, bool]:
    if not ocr_available():
        return (
            "",
            "OCR skipped: tesseract binary not found on PATH (or pytesseract/Pillow unavailable)",
            False,
        )
    from PIL import Image
    import pytesseract

    try:
        with Image.open(path) as img:
            text = pytesseract.image_to_string(img, timeout=OCR_TIMEOUT_S)
        note = None if text.strip() else "OCR ran but produced no text"
        return text, note, True
    except Exception as exc:
        return "", f"OCR failed: {exc}", True


def _ocr_pdf(path: Path) -> tuple[str, str | None, bool]:
    if not ocr_available():
        return (
            "",
            "OCR skipped: tesseract binary not found on PATH (or pytesseract/Pillow unavailable)",
            False,
        )
    import pymupdf
    from PIL import Image
    import pytesseract

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        return "", f"OCR failed: cannot open PDF: {exc}", True

    chunks: list[str] = []
    problems: list[str] = []
    try:
        for number, page in enumerate(doc, start=1):
            try:
                pix = page.get_pixmap(dpi=OCR_DPI)
                mode = {1: "L", 3: "RGB", 4: "RGBA"}.get(pix.n, "RGB")
                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                chunks.append(pytesseract.image_to_string(img, timeout=OCR_TIMEOUT_S))
            except Exception as exc:
                problems.append(f"page {number}: {exc}")
    finally:
        doc.close()
    note: str | None = "; ".join(problems) or None
    if not note and chunks and not any(chunk.strip() for chunk in chunks):
        note = "OCR ran but produced no text"
    return "\f".join(chunks), note, True


def _extract_pdf(path: Path) -> ExtractionResult:
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ExtractionError(f"cannot open PDF {path.name}: {exc}") from exc
    try:
        pages_text = [page.get_text("text") for page in doc]
    except Exception as exc:
        raise ExtractionError(f"cannot read PDF {path.name}: {exc}") from exc
    finally:
        doc.close()

    slots = max(len(pages_text), 1)
    total_chars = sum(len(text.strip()) for text in pages_text)
    if total_chars >= MIN_CHARS_PER_PAGE * slots:
        return ExtractionResult(
            text="\f".join(pages_text),
            method="pdf",
            ocr_used=False,
            note=None,
            pages=len(pages_text),
        )

    text, note, ran = _ocr_pdf(path)
    if ran:
        return ExtractionResult(
            text=text,
            method="ocr",
            ocr_used=bool(text.strip()),
            note=note,
            pages=len(pages_text),
        )
    return ExtractionResult(
        text="\f".join(pages_text),
        method="ocr",
        ocr_used=False,
        note=note,
        pages=len(pages_text),
    )


def extract(path: Path | str, *, content_type: str | None = None) -> ExtractionResult:
    """Extract raw text from a stored document.

    Args:
        path: Path of the raw document (``storage/raw/...``).
        content_type: MIME type hint from the fetch stage.

    Returns:
        ExtractionResult carrying text, method, OCR state and a situation note.

    Raises:
        ExtractionError: If the file is missing, empty or unreadable.
        UnsupportedFormatError: If no extraction path recognises the bytes.
    """
    target = Path(path)
    if not target.is_file():
        raise ExtractionError(f"document not found: {target}")
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise ExtractionError(f"cannot read {target}: {exc}") from exc
    if not data:
        raise ExtractionError(f"document is empty: {target.name}")

    kind = _kind_for(target, data, content_type)
    if kind == "pdf":
        return _extract_pdf(target)
    if kind == "html":
        return ExtractionResult(
            text=_html_to_text(data), method="html", ocr_used=False, note=None, pages=1
        )
    if kind == "image":
        text, note, ran = _ocr_image(target)
        return ExtractionResult(
            text=text,
            method="ocr",
            ocr_used=bool(ran and text.strip()),
            note=note,
            pages=1,
        )
    return ExtractionResult(
        text=_decode_text(data), method="html", ocr_used=False, note=None, pages=1
    )
