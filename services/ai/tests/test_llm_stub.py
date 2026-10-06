"""StubLLM rule extraction + provider fallback unit tests (no network)."""

import pytest

from ai.llm import (LLMRequest, ResilientLLM, StubLLM, estimate_risk,
                    extract_effective_date, extract_headings,
                    extract_obligations, extract_reference_numbers, get_llm)
from sample_data import NEW_TEXT


def _request(**overrides) -> LLMRequest:
    defaults = dict(
        regulation_id=1, version_no=2, source="RBI",
        title="Master Direction - Digital Lending (Amended)",
        new_text=NEW_TEXT)
    defaults.update(overrides)
    return LLMRequest(**defaults)


def test_effective_date_dmy_with_context():
    assert extract_effective_date(
        "comes into force with effect from 1 November 2026") == "2026-11-01"


def test_effective_date_iso_with_context():
    assert extract_effective_date(
        "This direction is effective from 2026-12-15") == "2026-12-15"


def test_effective_date_absent_returns_none():
    assert extract_effective_date("The committee met on the subject today.") is None


def test_obligations_captured():
    obligations = extract_obligations(NEW_TEXT)
    assert obligations
    assert any("shall" in o.lower() or "must" in o.lower() for o in obligations)


def test_headings_detected():
    headings = extract_headings(NEW_TEXT)
    assert "1. Applicability" in headings
    assert "6. Penalties" in headings


def test_reference_numbers_extracted():
    references = extract_reference_numbers(NEW_TEXT)
    assert any("RBI/2026-27/45" in ref for ref in references)
    assert any("DNBR.PD.78" in ref for ref in references)


def test_risk_levels():
    assert estimate_risk(
        "Any contravention shall attract a penalty. "
        "The Bank may cancel the authorisation.") == "HIGH"
    assert estimate_risk("The committee met today and discussed matters.") == "LOW"


def test_stub_emits_normalized_fields():
    result = StubLLM().analyze(_request())
    assert set(result) == {
        "summary", "key_changes", "affected_entities", "effective_date",
        "required_actions", "risk_level"}
    assert result["effective_date"] == "2026-11-01"
    assert result["risk_level"] == "HIGH"


def test_stub_handles_missing_old_text():
    result = StubLLM().analyze(_request(
        old_text=None, diff_text="", added_lines=[], removed_lines=[],
        old_version_missing=True))
    assert "unavailable" in result["summary"].lower()


class _BrokenPrimary:
    mode = "llm"
    model = "broken-model"

    def analyze(self, req):
        raise RuntimeError("provider down")


def test_resilient_llm_falls_back_to_stub():
    resilient = ResilientLLM(_BrokenPrimary())
    result = resilient.analyze(_request())
    assert resilient.mode == "stub"
    assert resilient.model == "stub-rules"
    assert resilient.last_error and "provider down" in resilient.last_error
    assert result["effective_date"] == "2026-11-01"


def test_get_llm_without_keys_is_stub():
    llm = get_llm()
    assert llm.mode == "stub"
    assert llm.model == "stub-rules"


def test_get_llm_force_stub(monkeypatch):
    monkeypatch.setenv("AI_FORCE_STUB", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    from ai import config
    config.clear_provider_cache()
    llm = get_llm()
    assert llm.mode == "stub"
    config.clear_provider_cache()


@pytest.mark.parametrize("key_var", ["OPENAI_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY"])
def test_provider_selection(monkeypatch, key_var):
    from ai import config
    monkeypatch.setenv(key_var, "test-key-123")
    config.clear_provider_cache()
    provider = config.llm_provider_config()
    assert provider["api_key"] == "test-key-123"
    assert provider["model"]
    if key_var == "GEMINI_API_KEY":
        assert provider["base_url"].startswith("https://generativelanguage.googleapis.com")
    config.clear_provider_cache()
