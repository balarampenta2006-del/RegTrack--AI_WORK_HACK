"""Text normalisation per the problem statement.

Rules applied in order:
1. newline normalisation (``\\r\\n``/``\\r`` -> ``\\n``)
2. Unicode NFKC (ligatures, full-width forms, circled digits, NBSP)
3. smart quotes / dashes / ellipsis / soft hyphens unified
4. page-number lines and repeated headers/footers stripped heuristically
5. line-end hyphenation (``-`` at EOL) re-joined
6. whitespace collapsed while preserving paragraph structure (``\\n\\n``)
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

PAGE_SEPARATOR = "\f"

_PAGE_NUM_RE = re.compile(
    r"^\s*(?:page\s*)?[-+]?\s*\d{1,4}\s*(?:of\s*\d{1,4})?[-+]?\s*$",
    re.IGNORECASE,
)
_HYPHEN_EOL_RE = re.compile(r"(?<=[A-Za-z])-\n(?=[a-z])")
_MULTI_SPACE_RE = re.compile(r"[^\S\n]+")
_LINE_EDGE_RE = re.compile(r" *\n *")
_BLANK_RUN_RE = re.compile(r"\n{3,}")

_CHAR_MAP = {
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'",
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"',
    0x2013: "-", 0x2014: "-", 0x2015: "-", 0x2212: "-",
    0x2026: "...",
    0x00AD: "",
    0x2022: "-",
}


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text)
    return text.translate(_CHAR_MAP)


def _edge_indices(lines: list[str]) -> tuple[int | None, int | None]:
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
    return first, last


def _drop_edge_page_numbers(page: str) -> str:
    lines = page.split("\n")
    first, last = _edge_indices(lines)
    if first is None:
        return page
    removed: set[int] = set()
    if _PAGE_NUM_RE.match(lines[first]):
        removed.add(first)
    if last is not None and last != first and _PAGE_NUM_RE.match(lines[last]):
        removed.add(last)
    if not removed:
        return page
    return "\n".join(line for i, line in enumerate(lines) if i not in removed)


def _normalise_edge(page: str, *, first: bool) -> str:
    lines = page.split("\n")
    if first:
        index = next((i for i, line in enumerate(lines) if line.strip()), None)
    else:
        index = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
    if index is None:
        return ""
    return " ".join(lines[index].split()).lower()


def _drop_repeated_edges(pages: list[str]) -> list[str]:
    threshold = max(2, -(-len(pages) // 3))
    first_counts = Counter(_normalise_edge(page, first=True) for page in pages)
    last_counts = Counter(_normalise_edge(page, first=False) for page in pages)
    drop_first = {line for line, count in first_counts.items() if line and count >= threshold}
    drop_last = {line for line, count in last_counts.items() if line and count >= threshold}

    cleaned_pages: list[str] = []
    for page in pages:
        lines = page.split("\n")
        first, last = _edge_indices(lines)
        removed: set[int] = set()
        if first is not None:
            candidate = " ".join(lines[first].split()).lower()
            if candidate in drop_first:
                removed.add(first)
        if last is not None and last not in removed:
            candidate = " ".join(lines[last].split()).lower()
            if candidate in drop_last:
                removed.add(last)
        cleaned_pages.append(
            page if not removed else "\n".join(
                line for i, line in enumerate(lines) if i not in removed
            )
        )
    return cleaned_pages


def _strip_page_artifacts(text: str) -> str:
    if PAGE_SEPARATOR not in text:
        return text
    pages = text.split(PAGE_SEPARATOR)
    if len(pages) >= 2:
        pages = [_drop_edge_page_numbers(page) for page in pages]
    if len(pages) >= 3:
        pages = _drop_repeated_edges(pages)
    return "\n".join(pages)


def clean_text(text: str) -> str:
    """Normalise extracted text into the canonical processed form.

    Args:
        text: Raw extracted text (form-feed separates PDF pages).

    Returns:
        Cleaned UTF-8 text with unified characters, no page furniture and
        paragraph structure preserved as blank lines.
    """
    if not text:
        return ""
    text = _normalise(text)
    text = _strip_page_artifacts(text)
    text = _LINE_EDGE_RE.sub("\n", text)
    text = _HYPHEN_EOL_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _LINE_EDGE_RE.sub("\n", text)
    text = _BLANK_RUN_RE.sub("\n\n", text)
    return text.strip()
