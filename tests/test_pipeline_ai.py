"""Pipeline accuracy fixtures for AI analysis (PLAN §2.4, ai role).

Author-level accuracy tests over the real services/ai package in stub mode
(no LLM key): analyzing a sample old/new gazette change must yield a
schema-valid §2.4 analysis with a non-empty summary, a null-or-ISO
effective_date, relevance levels inside the enum - be deterministic across
runs - and be persisted to storage/analysis/<id>/v<n>.json.

Everything runs against an isolated temporary STORAGE_ROOT; the live backend
is replaced by a scripted fake client, so no backend/docker interaction.
"""

import json
import uuid

import pytest

from pipeline_support import import_service_modules, service_available
from test_storage_contracts import (RELEVANCE_LEVELS, RISK_LEVELS,
                                    validate_analysis)

pytestmark = pytest.mark.skipif(
    not service_available("ai"),
    reason="services/ai not present yet (ai agent pending - will enable on re-run)")

SAMPLE_OLD = """RESERVE BANK OF INDIA
Notification on Digital Lending Platforms
1. All Regulated Entities shall ensure that the Loan Service Providers follow
fair practices Code.
Issue: August 15, 2026"""

SAMPLE_NEW = """RESERVE BANK OF INDIA
Notification on Digital Lending Platforms (Amended)
1. All Regulated Entities shall ensure that the Loan Service Providers follow
fair practices Code.
2. Regulated Entities shall maintain a public register of loan service
providers within 30 days.
Issue: October 01, 2026"""

STABLE_KEYS = ("analysis_mode", "model", "summary", "key_changes",
               "affected_entities", "effective_date", "required_actions",
               "risk_level", "relevance")


class FakeBackendClient:
    """Scripted stand-in for BackendClient (no HTTP, no docker)."""

    def __init__(self, regulation_title: str = "Notification on Digital Lending Platforms"):
        self.regulation_title = regulation_title

    def get_regulation(self, regulation_id: int) -> dict:
        return {"id": regulation_id, "title": self.regulation_title,
                "sourceCode": "RBI"}

    def get_versions(self, regulation_id: int) -> list[dict]:
        return []  # no backend versions: storage text only

    def get_version(self, regulation_id: int, version_id: int) -> dict:
        return {}

    def get_companies(self) -> list[dict]:
        return [{"id": 1, "name": "QA Fintech Ltd", "industry": "Banking & NBFC"}]

    def get_profile(self, company_id: int) -> dict:
        return {
            "industrySectors": "NBFC, Digital lending, Payments",
            "regulatoryBodies": "RBI",
            "jurisdictions": "India",
            "complianceContactEmail": "qa@fintech.test",
        }

    def close(self) -> None:  # required by run_analysis bookkeeping
        pass


class FakeVectorStore:
    backend = "qa-fake"

    def upsert(self, chunks) -> int:
        return len(chunks)

    def close(self) -> None:
        pass


@pytest.fixture
def ai_env(monkeypatch, tmp_path):
    """Import services/ai with stub mode forced and an isolated storage root."""
    storage = tmp_path / "storage"
    monkeypatch.setenv("STORAGE_ROOT", str(storage))
    monkeypatch.setenv("AI_FORCE_STUB", "1")
    monkeypatch.setenv("LLM_MODEL", "stub-rules")
    for var in ("LLM_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    modules, errors = import_service_modules("ai")
    if not modules:
        pytest.skip(f"services/ai: no modules importable ({errors[:3]})")

    config = next((m for m in modules if m.__name__.endswith(".config")), None)
    analyze = next((m for m in modules if m.__name__.endswith(".analyze")), None)
    if config is None or analyze is None:
        pytest.skip("services/ai: ai.config / ai.analyze not importable "
                    f"(errors={errors[:3]})")
    config.clear_provider_cache()

    return {
        "storage": storage,
        "config": config,
        "analyze": analyze,
        "errors": errors,
    }


def _reg_id() -> int:
    return 900_000 + uuid.uuid4().int % 90_000


def _write_versions(storage, reg_id: int, old_text: str | None, new_text: str):
    directory = storage / "processed" / str(reg_id)
    directory.mkdir(parents=True, exist_ok=True)
    if old_text is not None:
        (directory / "v1.txt").write_text(old_text, encoding="utf-8")
    (directory / "v2.txt").write_text(new_text, encoding="utf-8")


def _run(ai_env, reg_id: int, version_no: int = 2, old_text: str | None = SAMPLE_OLD,
         new_text: str = SAMPLE_NEW):
    _write_versions(ai_env["storage"], reg_id, old_text, new_text)
    result = ai_env["analyze"].run_analysis(
        reg_id, version_no,
        event_id=123456,
        emit=False,
        client=FakeBackendClient(),
        store=FakeVectorStore(),
    )
    return result.analysis if hasattr(result, "analysis") else dict(result)


# --------------------------------------------------------------------------
# Accuracy + contract
# --------------------------------------------------------------------------

def test_stub_analysis_returns_schema_valid_output(ai_env):
    analysis = _run(ai_env, _reg_id())

    errors = validate_analysis(analysis)
    assert not errors, f"analysis violates PLAN §2.4: {errors}"

    assert analysis["analysis_mode"] == "stub", "expected stub mode (no key)"
    assert analysis["model"] == "stub-rules"
    assert analysis["summary"].strip(), "summary must be non-empty"
    assert analysis["effective_date"] is None or isinstance(
        analysis["effective_date"], str)
    assert analysis["risk_level"] in RISK_LEVELS
    assert analysis["relevance"], "relevance list must not be empty"
    for item in analysis["relevance"]:
        assert item["level"] in RELEVANCE_LEVELS
        assert item["rationale"].strip()
    assert analysis["event_id"] == 123456


def test_stub_analysis_detects_the_new_clause(ai_env):
    analysis = _run(ai_env, _reg_id())
    blob = " ".join([analysis["summary"], *analysis["key_changes"],
                     *analysis["required_actions"]]).lower()
    assert "public register" in blob, (
        f"new regulatory clause not surfaced in analysis: {blob[:400]!r}")
    assert "public register" in " ".join(analysis["key_changes"]).lower()


def test_stub_analysis_relevance_scoring(ai_env):
    analysis = _run(ai_env, _reg_id())
    relevance = analysis["relevance"]
    entry = next((r for r in relevance if r["company_id"] == 1), None)
    assert entry is not None, "profiled company missing from relevance"
    assert entry["level"] in RELEVANCE_LEVELS
    assert entry["level"] == "HIGH", (
        f"RBI-regulated NBFC profile should score HIGH: {entry['rationale']}")
    assert "Score" in entry["rationale"]


def test_stub_analysis_is_deterministic(ai_env):
    reg_id = _reg_id()
    first = _run(ai_env, reg_id)
    second = _run(ai_env, reg_id)

    for key in STABLE_KEYS:
        assert key in first, f"missing key {key}"
        assert first[key] == second[key], (
            f"non-deterministic field {key}: {first[key]!r} != {second[key]!r}")


def test_stub_analysis_effective_date_is_null_or_iso(ai_env):
    analysis = _run(ai_env, _reg_id())
    eff = analysis["effective_date"]
    assert eff is None or (isinstance(eff, str) and len(eff) == 10 and eff[4] == "-")


def test_stub_analysis_single_version_marks_old_missing(ai_env):
    reg_id = _reg_id()
    analysis = _run(ai_env, reg_id, old_text=None)
    assert analysis.get("old_version_missing") is True
    assert validate_analysis(analysis) == []
    assert analysis["summary"].strip()


def test_analysis_persisted_to_storage_contract_path(ai_env):
    reg_id = _reg_id()
    _run(ai_env, reg_id)

    path = ai_env["storage"] / "analysis" / str(reg_id) / "v2.json"
    assert path.is_file(), f"analysis file missing: {path}"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert validate_analysis(saved) == []
    assert saved["regulation_id"] == reg_id
    assert saved["version_no"] == 2


def test_analysis_key_changes_are_strings_and_bounded(ai_env):
    analysis = _run(ai_env, _reg_id())
    for key in ("key_changes", "affected_entities", "required_actions"):
        value = analysis[key]
        assert isinstance(value, list) and value, f"{key} must be a non-empty list"
        assert all(isinstance(v, str) and v.strip() for v in value)
        assert len(value) <= 12, f"{key} exceeds the contract cap"
