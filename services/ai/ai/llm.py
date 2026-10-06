"""LLM integration: OpenAI-compatible client with a deterministic StubLLM fallback.

Provider selection (PLAN.md §2.2):
  OPENAI_API_KEY -> OpenAI (or OPENAI_BASE_URL)
  GEMINI_API_KEY -> Gemini OpenAI-compatible endpoint (GEMINI_BASE_URL)
  LLM_API_KEY    -> generic OpenAI-compatible endpoint (LLM_BASE_URL)

If no key is configured, or the provider fails at runtime, analysis falls back to
:class:`StubLLM` - a purely rule-based extractor that still emits a schema-valid
result. The pipeline must never crash because of a missing/broken LLM key.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import config

log = logging.getLogger(__name__)

STUB_MODEL = "stub-rules"


# ---------------------------------------------------------------------------
# request payload
# ---------------------------------------------------------------------------
@dataclass
class LLMRequest:
    regulation_id: int
    version_no: int
    source: str
    title: str
    new_text: str
    old_text: str | None = None
    diff_text: str = ""
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    old_version_missing: bool = False


# ---------------------------------------------------------------------------
# deterministic rule helpers (shared with StubLLM, unit-tested directly)
# ---------------------------------------------------------------------------
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DATE_CONTEXT = re.compile(
    r"(?:effective|w\.?\s*e\.?\s*f\.?|with\s+effect\s+from|comes?\s+into\s+force"
    r"|from\s+the\s+(?:date\s+of\s+)?(?:publication|issue)|on\s+or\s+before)",
    re.IGNORECASE,
)

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:-|/|\s)?\s*({_MONTH_RE})[a-z]*,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)
_MDY_RE = re.compile(
    rf"\b({_MONTH_RE})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
    re.IGNORECASE,
)

_OBLIGATION_RE = re.compile(
    r"\b(?:shall|must|must\s+not|shall\s+not|is\s+required\s+to|are\s+required\s+to"
    r"|is\s+mandated\s+to|may\s+not|should)\b",
    re.IGNORECASE,
)
_PENALTY_WORDS = re.compile(
    r"\b(?:penalt(?:y|ies)|fine[ds]?|prosecut(?:e|ed|ion)|contravention"
    r"|contraven(?:e|ing)|show\s+cause|cancel(?:lation|led)?|revoke[ds]?"
    r"|blacklist\w*|suspend(?:ed|sion)?|licence\s+cancel|imprison\w*)\b",
    re.IGNORECASE,
)

_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"\d+(?:\.\d+)*\s*[\.\)]\s+\S"          # 1. / 1.2.1 style
    r"|[IVXLC]+\s*[\.\)]\s+\S"              # roman numerals
    r"|[A-Z]\s*[\.\)]\s+\S"                 # a. / A.
    r"|[A-Z][A-Z0-9 &/,\'\-]{5,}$"          # ALL CAPS lines
    r")",
)

_REFERENCE_RES = [
    re.compile(r"\b(?:Notification|Circular|Press\s+Release|Order|Direction|Office\s+Memorandum)"
               r"\s*(?:No\.?|Number)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\.\-/]{2,40})", re.I),
    re.compile(r"\b((?:F\.?\s*No\.?)\s*[A-Z0-9][A-Z0-9\.\-/]{2,40})", re.I),
    re.compile(r"\b(G\.?\s*S\.?\s*R\.?\s*\d{1,5}\s*\(\s*E\s*\))"),
    re.compile(r"\b(RBI/[A-Z]{2,3}/?\d{4}-\d{2}/\d{1,5})"),
    re.compile(r"\b(RBI/\d{4}-\d{2}/\d{1,5})"),
    re.compile(r"\b([A-Z]{1,5}\d{1,6}/\d{2,4}[-/]\d{1,4}\b(?:/\d{1,4})?)"),
    re.compile(r"\b(DOR(?:\.[A-Z0-9]+){3,}\.\d+\.\d+)\b"),
]

_ENTITY_TERMS = [
    "regulated entities", "scheduled commercial banks", "banks", "nbfc",
    "non-banking financial companies", "housing finance companies",
    "microfinance institutions", "digital lenders", "loan service providers",
    "listed entities", "listed companies", "intermediaries", "stock brokers",
    "asset management companies", "mutual funds", "depositories", "credit rating agencies",
    "payment system operators", "payment aggregators", "authorised persons",
    "authorized persons", "udfis", "fintechs", "companies", "directors",
    "key managerial personnel", "members", "issuers", "primary dealers",
]


def _valid_date(year: int, month: int, day: int) -> str | None:
    if not (1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2100):
        return None
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_effective_date(text: str) -> str | None:
    """Regex-extract an effective date as YYYY-MM-DD (None when absent)."""
    if not text:
        return None

    # ISO dates first (unambiguous)
    for match in _ISO_DATE_RE.finditer(text):
        start = max(0, match.start() - 80)
        window = text[start:match.end() + 80]
        normalized = _valid_date(int(match.group(1)), int(match.group(2)),
                                 int(match.group(3)))
        if normalized and (_DATE_CONTEXT.search(window) or "effective" in window.lower()):
            return normalized

    for match in _DMY_RE.finditer(text):
        start = max(0, match.start() - 80)
        window = text[start:match.end() + 80]
        day, month_token, year = match.group(1), match.group(2).lower(), match.group(3)
        normalized = _valid_date(int(year), _MONTHS[month_token], int(day))
        if normalized and _DATE_CONTEXT.search(window):
            return normalized

    for match in _MDY_RE.finditer(text):
        start = max(0, match.start() - 80)
        window = text[start:match.end() + 80]
        month_token, day, year = match.group(1).lower(), match.group(2), match.group(3)
        normalized = _valid_date(int(year), _MONTHS[month_token], int(day))
        if normalized and _DATE_CONTEXT.search(window):
            return normalized

    return None


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;!?])\s+|\n+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def extract_obligations(text: str, limit: int = 6) -> list[str]:
    """Sentences containing SHALL/MUST/... obligations (capped, deduped)."""
    out: list[str] = []
    for sentence in _split_sentences(text):
        if len(sentence) < 15 or len(sentence) > 600:
            continue
        if _OBLIGATION_RE.search(sentence):
            cleaned = re.sub(r"\s+", " ", sentence).strip()
            if cleaned.lower() not in {o.lower() for o in out}:
                out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def extract_headings(text: str, limit: int = 25) -> list[str]:
    out: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped and _HEADING_RE.match(stripped) and len(stripped) <= 160:
            if stripped.lower() not in {h.lower() for h in out}:
                out.append(stripped)
        if len(out) >= limit:
            break
    return out


def extract_reference_numbers(text: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for pattern in _REFERENCE_RES:
        for match in pattern.finditer(text or ""):
            value = re.sub(r"\s+", " ", match.group(1)).strip().rstrip(",;")
            key = value.lower()
            if key and key not in seen:
                seen.add(key)
                out.append(value)
            if len(out) >= limit:
                return out
    return out


def extract_entities(text: str, source: str = "", limit: int = 8) -> list[str]:
    lowered = (text or "").lower()
    found: list[str] = []
    for term in _ENTITY_TERMS:
        if term in lowered and term not in {f.lower() for f in found}:
            found.append(term)
        if len(found) >= limit:
            break
    if not found and source:
        found = [f"entities regulated by {source.upper()}"]
    return found


def estimate_risk(text: str) -> str:
    penalty_hits = len(_PENALTY_WORDS.findall(text or ""))
    obligation_hits = len(_OBLIGATION_RE.findall(text or ""))
    if penalty_hits >= 3 or re.search(r"\bshow\s+cause\b", text or "", re.I):
        return "HIGH"
    if penalty_hits >= 1 or obligation_hits >= 4:
        return "MEDIUM"
    if obligation_hits >= 1:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# normalization / validation of LLM output
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = (
    "summary", "key_changes", "affected_entities", "effective_date",
    "required_actions", "risk_level",
)


def _as_str_list(value: Any, limit: int = 12) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [ln for ln in re.split(r"[\n;•]+", value) if ln.strip()]
        return [re.sub(r"\s+", " ", it).strip(" -")[:400] for it in items if it.strip()][:limit]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if item is None:
                continue
            text = re.sub(r"\s+", " ", str(item)).strip()
            if text:
                out.append(text[:400])
        return out[:limit]
    text = str(value).strip()
    return [text[:400]] if text else []


def normalize_analysis_fields(raw: dict) -> dict:
    """Coerce an LLM/stub payload into the PLAN.md §2.4 analysis field types."""
    raw = raw or {}
    summary = re.sub(r"\s+", " ", str(raw.get("summary") or "")).strip()
    effective_date = raw.get("effective_date")
    if effective_date in (None, "", "null", "None", "N/A", "TBD"):
        effective_date = None
    else:
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(effective_date))
        if match:
            normalized = _valid_date(int(match.group(1)), int(match.group(2)),
                                     int(match.group(3)))
            effective_date = normalized
        else:
            effective_date = None

    risk = str(raw.get("risk_level") or "").strip().upper()
    if risk not in {"HIGH", "MEDIUM", "LOW"}:
        risk = "MEDIUM"

    return {
        "summary": summary,
        "key_changes": _as_str_list(raw.get("key_changes")),
        "affected_entities": _as_str_list(raw.get("affected_entities")),
        "effective_date": effective_date,
        "required_actions": _as_str_list(raw.get("required_actions")),
        "risk_level": risk,
    }


# ---------------------------------------------------------------------------
# stub (deterministic, rule based)
# ---------------------------------------------------------------------------
class StubLLM:
    """Rule-based analyzer used when no key is set or a provider fails."""

    mode = "stub"
    model = STUB_MODEL

    def analyze(self, req: LLMRequest) -> dict:
        new_text = req.new_text or ""
        added = [ln.strip() for ln in (req.added_lines or []) if ln.strip()]

        summary_bits: list[str] = []
        if req.source:
            summary_bits.append(f"{req.source.upper()} published an update of "
                                f"\"{req.title or 'regulation'}\" (v{req.version_no}).")
        if req.old_version_missing:
            summary_bits.append("Previous version unavailable; analyzed current text only.")
        elif added:
            summary_bits.append(f"{len(added)} line(s) added, "
                                f"{len(req.removed_lines or [])} line(s) removed.")
        first_para = next(
            (re.sub(r"\s+", " ", ln).strip()
             for ln in new_text.splitlines()
             if len(ln.strip()) > 60 and not _HEADING_RE.match(ln.strip())),
            "",
        )
        if first_para:
            summary_bits.append(first_para[:320])
        summary = " ".join(summary_bits)[:700] or "No extractable summary."

        if added:
            key_changes = []
            for line in added[:10]:
                line = re.sub(r"\s+", " ", line).strip()
                if line and line.lower() not in {k.lower() for k in key_changes}:
                    key_changes.append(line[:300])
        else:
            headings = extract_headings(new_text)
            key_changes = headings[:8]
        if not key_changes:
            key_changes = ["Content updated; no distinct change lines identified."]

        effective_date = extract_effective_date(new_text)
        obligations = extract_obligations(new_text)
        required_actions = [o[:400] for o in obligations]
        if effective_date:
            required_actions.append(
                f"Implement compliance measures before {effective_date}.")
        if not required_actions:
            required_actions = [
                "Review the updated text and align internal policies."]

        references = extract_reference_numbers(new_text)
        if references:
            required_actions.append(
                f"Verify reference document(s): {', '.join(references)}.")

        return normalize_analysis_fields({
            "summary": summary,
            "key_changes": key_changes,
            "affected_entities": extract_entities(
                f"{new_text} {req.title or ''} {req.source or ''}", req.source),
            "effective_date": effective_date,
            "required_actions": required_actions,
            "risk_level": estimate_risk(new_text),
        })


# ---------------------------------------------------------------------------
# real OpenAI-compatible client
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a senior regulatory compliance analyst. You compare two versions of a "
    "regulation and extract a machine-readable change analysis. Respond with STRICT "
    "JSON only - no markdown fences, no commentary - using exactly these keys:\n"
    '{"summary": string (<=600 chars),\n'
    ' "key_changes": string[] (<=10 concrete changes),\n'
    ' "affected_entities": string[] (<=8),\n'
    ' "effective_date": "YYYY-MM-DD" or null,\n'
    ' "required_actions": string[] (<=8 concrete compliance actions),\n'
    ' "risk_level": "HIGH" | "MEDIUM" | "LOW"}\n'
    "Rules: effective_date must be null when the text states no date; risk_level is "
    "HIGH for penalties/licence cancellation, MEDIUM for new obligations, LOW for "
    "editorial changes."
)


def build_messages(req: LLMRequest) -> list[dict]:
    old_excerpt = (req.old_text or "")[:6000]
    new_excerpt = (req.new_text or "")[:8000]
    user_payload = {
        "regulation_id": req.regulation_id,
        "version_no": req.version_no,
        "source": req.source,
        "title": req.title,
        "old_version_missing": req.old_version_missing,
        "diff": (req.diff_text or "")[:4000],
        "added_lines": (req.added_lines or [])[:40],
        "removed_lines": (req.removed_lines or [])[:40],
        "old_text_excerpt": old_excerpt,
        "new_text_excerpt": new_excerpt,
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def _extract_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("LLM returned non-object JSON")
    return parsed


class OpenAILLM:
    mode = "llm"

    def __init__(self, api_key: str, model: str, base_url: str | None = None,
                 timeout: float | None = None, max_retries: int | None = None):
        from openai import OpenAI  # guarded import

        self.model = model
        self.provider_base_url = base_url
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        kwargs["timeout"] = timeout if timeout is not None else config.llm_timeout()
        kwargs["max_retries"] = max_retries if max_retries is not None else config.llm_retries()
        self._client = OpenAI(**kwargs)

    def analyze(self, req: LLMRequest) -> dict:
        messages = build_messages(req)
        content = self._complete(messages, json_mode=True)
        raw = _extract_json(content)
        return normalize_analysis_fields(raw)

    def _complete(self, messages: list[dict], json_mode: bool) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            if json_mode:
                # some OpenAI-compatible gateways reject response_format
                log.warning("json_mode failed (%s); retrying without response_format", exc)
                kwargs.pop("response_format", None)
                response = self._client.chat.completions.create(**kwargs)
            else:
                raise
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("LLM returned no choices")
        message = choices[0].message
        content = getattr(message, "content", None)
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content


class ResilientLLM:
    """Never raises: any provider failure degrades to StubLLM."""

    def __init__(self, primary: BaseLLMTypes | None = None):
        self._primary = primary
        self._stub = StubLLM()
        self._fell_back = primary is None
        self.last_error: str | None = None

    @property
    def mode(self) -> str:
        return "stub" if self._fell_back else "llm"

    @property
    def model(self) -> str:
        if self._fell_back or self._primary is None:
            return self._stub.model
        return self._primary.model

    def analyze(self, req: LLMRequest) -> dict:
        if self._primary is not None and not self._fell_back:
            try:
                result = self._primary.analyze(req)
                return normalize_analysis_fields(result)
            except Exception as exc:  # noqa: BLE001 - deliberate total fallback
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._fell_back = True
                log.warning("LLM provider failed, falling back to StubLLM: %s",
                            self.last_error)
        return self._stub.analyze(req)


BaseLLMTypes = Any  # StubLLM | OpenAILLM | ResilientLLM


def get_llm() -> ResilientLLM:
    """Factory honoring env vars; returns stub-only client when unconfigured."""
    if config.force_stub():
        log.info("AI_FORCE_STUB set -> StubLLM")
        return ResilientLLM(None)

    provider = config.llm_provider_config()
    if not provider:
        log.info("No LLM API key configured -> StubLLM")
        return ResilientLLM(None)

    try:
        primary = OpenAILLM(
            api_key=provider["api_key"],
            model=provider["model"],
            base_url=provider.get("base_url"),
            timeout=config.llm_timeout(),
            max_retries=config.llm_retries(),
        )
    except Exception as exc:  # pragma: no cover - import/client construction
        log.warning("Could not construct LLM client (%s); using StubLLM", exc)
        return ResilientLLM(None)

    log.info("LLM provider=%s model=%s", provider["provider"], provider["model"])
    return ResilientLLM(primary)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
