"""Snapshot store and change detection.

Layout per source (PLAN.md §2.3 ``storage/snapshots/<code>/``)::

    storage/snapshots/RBI/
        latest.txt            clean extracted text (canonical for hashing)
        latest.html           raw HTML
        latest.meta.json      url/title/sha256/fetched_at/engine/status_code
        history/<ts>.txt      timestamped text snapshots
        history/<ts>.html     timestamped raw HTML snapshots
        diffs/<ts>.diff       unified diff old -> new (written on change)

Change detection: sha256 of the clean text vs the stored ``latest.txt``;
a difference triggers a ``difflib.unified_diff`` persisted under ``diffs/``.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .retriever import FetchResult

log = logging.getLogger("monitor.snapshots")


def _now_label() -> str:
    """Fixed-width sortable timestamp label: ``YYYYmmddTHHMMSSffffff``."""
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%Y%m%dT%H%M%S')}{now.microsecond:06d}"


def _unique_stamp(directory: Path, extensions: tuple[str, ...]) -> str:
    """Timestamp label that never overwrites existing files in ``directory``.

    Clock granularity can produce identical labels within one fast test run;
    collisions get a ``_N`` suffix which still sorts chronologically.
    """
    base = _now_label()
    stamp = base
    counter = 0
    while any((directory / f"{stamp}{ext}").exists() for ext in extensions):
        counter += 1
        stamp = f"{base}_{counter}"
    return stamp


def sha256_text(text: str) -> str:
    """Hex sha256 of the UTF-8 encoded clean text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    """A stored snapshot of one source."""

    source_code: str
    text_path: Path
    html_path: Path
    meta_path: Path
    text: str
    meta: dict


class SnapshotStore:
    """Filesystem-backed snapshot store scoped to ``storage/snapshots/``."""

    def __init__(self, root: Path) -> None:
        """Args:
            root: Snapshot root directory (``storage/snapshots``).
        """
        self.root = Path(root)

    def code_dir(self, code: str) -> Path:
        """Directory for one source code (created on demand)."""
        path = self.root / code.upper()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load_latest(self, code: str) -> Snapshot | None:
        """Load the latest snapshot for ``code``.

        Args:
            code: Source code such as ``RBI``.

        Returns:
            The stored :class:`Snapshot`, or ``None`` when no baseline exists.
        """
        code = code.upper()
        text_path = self.root / code / "latest.txt"
        if not text_path.exists():
            return None
        text = text_path.read_text(encoding="utf-8")
        meta_path = self.root / code / "latest.meta.json"
        meta: dict = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("unreadable meta for %s (%s); continuing with text only", code, exc)
        return Snapshot(
            source_code=code,
            text_path=text_path,
            html_path=self.root / code / "latest.html",
            meta_path=meta_path,
            text=text,
            meta=meta,
        )

    def save(self, code: str, fetched: FetchResult, sha256: str) -> Snapshot:
        """Persist ``fetched`` as latest + timestamped history for ``code``.

        Args:
            code: Source code such as ``RBI``.
            fetched: Retrieval result to store.
            sha256: Precomputed hex sha256 of ``fetched.text``.

        Returns:
            The stored :class:`Snapshot`.
        """
        code = code.upper()
        directory = self.code_dir(code)
        history = directory / "history"
        history.mkdir(exist_ok=True)
        stamp = _unique_stamp(history, (".txt", ".html"))
        meta = {
            "source_code": code,
            "url": fetched.url,
            "title": fetched.title,
            "engine": fetched.engine,
            "status_code": fetched.status_code,
            "fetched_at": fetched.fetched_at,
            "sha256": sha256,
        }
        text_path = directory / "latest.txt"
        html_path = directory / "latest.html"
        meta_path = directory / "latest.meta.json"
        text_path.write_text(fetched.text, encoding="utf-8")
        html_path.write_text(fetched.html, encoding="utf-8")
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")

        (history / f"{stamp}.txt").write_text(fetched.text, encoding="utf-8")
        (history / f"{stamp}.html").write_text(fetched.html, encoding="utf-8")
        log.info("snapshot saved for %s at %s", code, stamp)
        return Snapshot(
            source_code=code,
            text_path=text_path,
            html_path=html_path,
            meta_path=meta_path,
            text=fetched.text,
            meta=meta,
        )

    def write_diff(self, code: str, old_text: str, new_text: str) -> Path:
        """Persist a unified diff between ``old_text`` and ``new_text``.

        Args:
            code: Source code such as ``RBI``.
            old_text: Previous snapshot text ("" for the first snapshot).
            new_text: New snapshot text.

        Returns:
            Path of the written ``.diff`` file.
        """
        code = code.upper()
        diffs_dir = self.code_dir(code) / "diffs"
        diffs_dir.mkdir(exist_ok=True)
        diff_path = diffs_dir / f"{_unique_stamp(diffs_dir, ('.diff',))}.diff"
        lines = difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"{code}/old",
            tofile=f"{code}/new",
            lineterm="",
        )
        diff_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("change diff written for %s: %s", code, diff_path.name)
        return diff_path
