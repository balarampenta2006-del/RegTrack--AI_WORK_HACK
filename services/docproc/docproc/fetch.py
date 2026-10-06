"""Document retrieval into ``storage/raw/`` (httpx for URLs, copy for paths)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .exceptions import FetchError

MAX_BYTES = 50 * 1024 * 1024
DEFAULT_TIMEOUT = httpx.Timeout(30.0)
USER_AGENT = "regtrack-docproc/1.0"

_EXT_BY_CT = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tif",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


@dataclass(frozen=True)
class FetchedDocument:
    """A document materialised under ``storage/raw/``."""

    path: Path
    source: str
    source_url: str
    content_type: str
    size: int


def is_url(spec: str) -> bool:
    """Return True when *spec* is an http(s) URL."""
    return bool(re.match(r"^https?://", spec.strip(), re.IGNORECASE))


def detect_content_type(data: bytes, header_ct: str | None = None, name: str = "") -> str:
    """Detect the content type of *data*.

    Magic bytes win over the server header (servers frequently mislabel PDFs),
    then the header, then the file suffix, then a UTF-8 decodability sniff.

    Args:
        data: Raw document bytes (at least the leading kilobyte matters).
        header_ct: Content-Type reported by the server, if any.
        name: File name used as a last-resort hint.

    Returns:
        A MIME type string (e.g. ``application/pdf``).
    """
    head = data[:1024]
    if head[:5] == b"%PDF-":
        return "application/pdf"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    lowered = head.lstrip().lower()
    if lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html") or b"<html" in lowered[:512]:
        return "text/html"
    if header_ct:
        ct = header_ct.split(";")[0].strip().lower()
        if ct:
            return ct
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".html", ".htm"}:
        return "text/html"
    if suffix in _IMAGE_SUFFIXES:
        return "image/" + ("jpeg" if suffix in {".jpg", ".jpeg"} else suffix.lstrip("."))
    if suffix in {".txt", ".md"}:
        return "text/plain"
    try:
        data.decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", unquote(name)).strip("._")
    return cleaned[:80] or "document"


def _destination(raw_dir: Path, spec: str, name_hint: str | None, content_type: str) -> Path:
    if is_url(spec):
        base = Path(urlparse(spec).path).name
    else:
        base = Path(spec).name
    base = _safe_name(base)
    if base == "document" or "." not in base:
        base += _EXT_BY_CT.get(content_type, "")
    digest = hashlib.sha256(spec.encode("utf-8")).hexdigest()[:8]
    prefix = f"{name_hint}_" if name_hint else ""
    return raw_dir / f"{prefix}{digest}_{base}"


def _fetch_url(spec: str, timeout: httpx.Timeout) -> tuple[bytes, str | None]:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            with client.stream("GET", spec) as response:
                response.raise_for_status()
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                    raise FetchError(f"document at {spec} exceeds {MAX_BYTES} bytes")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise FetchError(f"document at {spec} exceeds {MAX_BYTES} bytes")
                    chunks.append(chunk)
                return b"".join(chunks), response.headers.get("content-type")
    except FetchError:
        raise
    except httpx.HTTPError as exc:
        raise FetchError(f"failed to download {spec}: {exc}") from exc


def _read_local(spec: str) -> tuple[bytes, str]:
    if spec.startswith("file://"):
        parsed = urlparse(spec)
        path = Path(unquote(parsed.path))
        if re.match(r"^/[A-Za-z]:", str(path)):
            path = Path(str(path)[1:])
    else:
        path = Path(spec).expanduser()
    if not path.is_file():
        raise FetchError(f"input path does not exist or is not a file: {spec}")
    try:
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise FetchError(f"document {path} exceeds {MAX_BYTES} bytes")
        return path.read_bytes(), path.name
    except FetchError:
        raise
    except OSError as exc:
        raise FetchError(f"cannot read {path}: {exc}") from exc


def fetch(
    spec: str,
    *,
    raw_dir: Path,
    name_hint: str | None = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
) -> FetchedDocument:
    """Retrieve *spec* (URL or local path) into *raw_dir*.

    The destination name is deterministic (name hint + hash of the spec), so
    re-running the pipeline for the same input overwrites the same raw file.

    Args:
        spec: http(s) URL, ``file://`` URL, or local filesystem path.
        raw_dir: Target directory (``storage/raw``); created when missing.
        name_hint: Optional prefix such as ``reg1_v2``.
        timeout: httpx timeout applied to URL downloads.

    Returns:
        Metadata about the materialised raw file.

    Raises:
        FetchError: If the document cannot be downloaded or read.
    """
    spec = spec.strip()
    if not spec:
        raise FetchError("input must not be empty")
    header_ct: str | None = None
    if is_url(spec):
        data, header_ct = _fetch_url(spec, timeout)
        source_url = spec
        name_for_ct = Path(urlparse(spec).path).name
    else:
        data, name_for_ct = _read_local(spec)
        source_url = ""
    content_type = detect_content_type(data, header_ct, name_for_ct)
    destination = _destination(raw_dir, spec, name_hint, content_type)
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    except OSError as exc:
        raise FetchError(f"cannot write raw document to {destination}: {exc}") from exc
    return FetchedDocument(
        path=destination,
        source=spec,
        source_url=source_url,
        content_type=content_type,
        size=len(data),
    )
