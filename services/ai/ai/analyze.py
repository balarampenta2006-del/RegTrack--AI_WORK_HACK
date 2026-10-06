"""Analysis pipeline: diff -> LLM/stub extraction -> relevance -> §2.4 JSON."""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config
from .client import BackendClient, BackendError, strip_html
from .embeddings import VectorStore, chunk_text, get_vector_store
from .emit import emit_alerts, resolve_event_id
from .llm import (LLMRequest, ResilientLLM, get_llm, normalize_analysis_fields,
                  utc_now_iso)
from .relevance import build_context, fetch_company_profiles, score_all

log = logging.getLogger(__name__)

#: exact contract keys from PLAN.md §2.4 (downstream frontend + alerts depend on them)
CONTRACT_KEYS = (
    "regulation_id", "version_no", "event_id", "analysis_mode", "model",
    "summary", "key_changes", "affected_entities", "effective_date",
    "required_actions", "risk_level", "relevance", "generated_at",
)

RISK_LEVELS = ("HIGH", "MEDIUM", "LOW")
RELEVANCE_LEVELS = ("HIGH", "MEDIUM", "LOW", "NONE")


class AnalysisError(RuntimeError):
    pass


@dataclass
class RunResult:
    analysis: dict
    emission: dict = field(default_factory=dict)
    indexing: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# text loading (storage/processed preferred, backend content as fallback)
# ---------------------------------------------------------------------------
def _read(path: Path) -> str | None:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
    return None


def _backend_text(client: BackendClient | None, regulation_id: int,
                  version_no: int) -> str | None:
    if client is None:
        return None
    try:
        versions = client.get_versions(regulation_id) or []
    except BackendError as exc:
        log.warning("versions fetch failed for regulation %s: %s",
                    regulation_id, exc)
        return None
    target = next(
        (v for v in versions if int(v.get("versionNo") or -1) == int(version_no)),
        None)
    if not target:
        return None
    try:
        detail = client.get_version(regulation_id, int(target["id"]))
    except BackendError as exc:
        log.warning("version fetch failed: %s", exc)
        return None
    return strip_html(str(detail.get("content") or "")) or None


def load_texts(regulation_id: int, version_no: int,
               client: BackendClient | None = None) -> dict:
    """Return {old_text, new_text, old_version_missing, new_origin, old_origin}."""
    directory = config.processed_dir(regulation_id)
    new_path = directory / f"v{version_no}.txt"
    old_path = directory / f"v{version_no - 1}.txt"

    new_text = _read(new_path)
    new_origin = "storage" if new_text is not None else None
    if new_text is None:
        new_text = _backend_text(client, regulation_id, version_no)
        new_origin = "backend" if new_text is not None else None

    old_text = None
    old_origin = None
    if version_no > 1:
        old_text = _read(old_path)
        old_origin = "storage" if old_text is not None else None
        if old_text is None:
            old_text = _backend_text(client, regulation_id, version_no - 1)
            old_origin = "backend" if old_text is not None else None

    if new_text is None:
        raise AnalysisError(
            f"no content for regulation {regulation_id} v{version_no}: "
            f"expected {new_path} (or backend fallback)")

    return {
        "old_text": old_text,
        "new_text": new_text,
        "old_version_missing": old_text is None,
        "new_origin": new_origin,
        "old_origin": old_origin,
    }


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------
def compute_diff(old_text: str | None, new_text: str) -> dict:
    old_lines = (old_text or "").splitlines()
    new_lines = (new_text or "").splitlines()
    if old_text is None:
        return {
            "diff_text": "",
            "added_lines": [],
            "removed_lines": [],
            "old_missing": True,
        }
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines, fromfile="old", tofile="new", lineterm=""))
    added = [ln[1:].strip() for ln in diff_lines
             if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()]
    removed = [ln[1:].strip() for ln in diff_lines
               if ln.startswith("-") and not ln.startswith("---") and ln[1:].strip()]
    return {
        "diff_text": "\n".join(diff_lines),
        "added_lines": added,
        "removed_lines": removed,
        "old_missing": False,
    }


# ---------------------------------------------------------------------------
# validation + persistence
# ---------------------------------------------------------------------------
def validate_analysis(analysis: dict) -> None:
    missing = [key for key in CONTRACT_KEYS if key not in analysis]
    if missing:
        raise AnalysisError(f"analysis missing contract keys: {missing}")

    if analysis["risk_level"] not in RISK_LEVELS:
        raise AnalysisError(f"invalid risk_level: {analysis['risk_level']!r}")
    if analysis["effective_date"] is not None:
        if not isinstance(analysis["effective_date"], str):
            raise AnalysisError("effective_date must be string or null")
    for key in ("key_changes", "affected_entities", "required_actions"):
        if not isinstance(analysis[key], list) or not all(
                isinstance(item, str) for item in analysis[key]):
            raise AnalysisError(f"{key} must be list[str]")
    if analysis["analysis_mode"] not in ("llm", "stub"):
        raise AnalysisError(f"invalid analysis_mode: {analysis['analysis_mode']!r}")
    if not isinstance(analysis["relevance"], list):
        raise AnalysisError("relevance must be a list")
    for entry in analysis["relevance"]:
        if not isinstance(entry, dict):
            raise AnalysisError("relevance entry must be an object")
        for key in ("company_id", "company_name", "level", "rationale"):
            if key not in entry:
                raise AnalysisError(f"relevance entry missing {key}")
        if entry["level"] not in RELEVANCE_LEVELS:
            raise AnalysisError(f"invalid relevance level {entry['level']!r}")


def save_analysis(analysis: dict) -> Path:
    directory = config.analysis_dir(int(analysis["regulation_id"]))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"v{analysis['version_no']}.json"
    path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# vector indexing
# ---------------------------------------------------------------------------
def index_texts(regulation_id: int, version_no: int, source: str,
                old_text: str | None, new_text: str,
                store: VectorStore | None = None) -> dict:
    """Chunk + upsert old/new texts into the vector store (guarded)."""
    own_store = store is None
    try:
        store = store or get_vector_store()
        total = 0
        for label, text, version in (("old", old_text, version_no - 1),
                                     ("new", new_text, version_no)):
            if not text:
                continue
            chunks = chunk_text(
                text,
                base_id=f"{regulation_id}:v{version}:{label}",
                metadata={
                    "regulation_id": int(regulation_id),
                    "version_no": int(version),
                    "source": source or "",
                    "kind": label,
                },
            )
            total += store.upsert(chunks)
        return {"ok": True, "backend": getattr(store, "backend", "unknown"),
                "chunks": total}
    except Exception as exc:  # noqa: BLE001 - indexing must never break analysis
        log.warning("vector indexing failed: %s", exc)
        return {"ok": False, "backend": getattr(store, "backend", "unknown"),
                "chunks": 0, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if own_store:
            close = getattr(store, "close", None)
            if callable(close):
                close()


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
def _regulation_meta(client: BackendClient | None, regulation_id: int) -> dict:
    if client is None:
        return {"title": "", "source": ""}
    try:
        regulation = client.get_regulation(regulation_id) or {}
        return {
            "title": regulation.get("title") or "",
            "source": regulation.get("sourceCode") or "",
        }
    except BackendError as exc:
        log.warning("regulation meta fetch failed: %s", exc)
        return {"title": "", "source": ""}


def run_analysis(regulation_id: int, version_no: int,
                 event_id: int | None = None,
                 emit: bool = True,
                 client: BackendClient | None = None,
                 llm: ResilientLLM | None = None,
                 store: VectorStore | None = None,
                 offline: bool = False) -> RunResult:
    """Full pipeline. Never raises because of LLM/provider problems."""
    own_client = client is None and not offline
    client = client or (BackendClient() if not offline else None)

    try:
        meta = _regulation_meta(client, regulation_id)
        texts = load_texts(regulation_id, version_no, client)
        diff = compute_diff(texts["old_text"], texts["new_text"])

        request = LLMRequest(
            regulation_id=regulation_id,
            version_no=version_no,
            source=meta["source"],
            title=meta["title"],
            new_text=texts["new_text"],
            old_text=texts["old_text"],
            diff_text=diff["diff_text"],
            added_lines=diff["added_lines"],
            removed_lines=diff["removed_lines"],
            old_version_missing=texts["old_version_missing"],
        )

        llm = llm or get_llm()
        fields = normalize_analysis_fields(llm.analyze(request))

        # resolve change event once (used by both relevance context and emission)
        resolved_event = event_id
        event_note = "provided"
        if resolved_event is None and client is not None:
            resolved_event, event_note = resolve_event_id(
                client, regulation_id, None)
        elif resolved_event is None:
            event_note = "offline"

        profiles = fetch_company_profiles(client, offline=client is None)
        context = build_context(
            source_code=meta["source"],
            regulation_title=meta["title"],
            analysis_fields=fields,
            text=texts["new_text"],
        )
        relevance = score_all(profiles, context)

        analysis: dict[str, Any] = {
            "regulation_id": int(regulation_id),
            "version_no": int(version_no),
            "event_id": resolved_event,
            "analysis_mode": llm.mode,
            "model": llm.model,
            **fields,
            "relevance": relevance,
            "generated_at": utc_now_iso(),
        }
        if texts["old_version_missing"]:
            analysis["old_version_missing"] = True
        validate_analysis(analysis)
        path = save_analysis(analysis)

        indexing = index_texts(regulation_id, version_no, meta["source"],
                               texts["old_text"], texts["new_text"], store=store)

        emission: dict[str, Any] = {"status": "skipped", "reason": "emit disabled"}
        if emit and client is not None:
            emission = emit_alerts(analysis, event_id=resolved_event,
                                   client=client)
            emission.setdefault("event_note", event_note)
        elif not emit:
            emission = {"status": "skipped",
                        "reason": f"emit disabled (event: {event_note})"}
        else:
            emission = {"status": "skipped",
                        "reason": f"offline mode (event: {event_note})"}

        log.info("analysis written to %s (mode=%s)", path, analysis["analysis_mode"])
        return RunResult(analysis=analysis, emission=emission, indexing=indexing)
    finally:
        if own_client and client is not None:
            client.close()
