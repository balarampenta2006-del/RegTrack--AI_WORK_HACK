"""Offline contract tests: StubLLM path emits a PLAN.md §2.4-valid analysis."""

import json

import pytest

from ai.analyze import (CONTRACT_KEYS, AnalysisError, run_analysis,
                        validate_analysis)


def test_stub_analysis_contains_every_contract_key(processed_storage,
                                                   fake_client):
    result = run_analysis(regulation_id=1, version_no=2, emit=False,
                          client=fake_client)
    analysis = result.analysis

    reloaded = json.loads(json.dumps(analysis))  # must survive JSON round trip
    for key in CONTRACT_KEYS:
        assert key in reloaded, f"missing contract key: {key}"

    assert analysis["analysis_mode"] == "stub"
    assert analysis["model"] == "stub-rules"
    assert analysis["regulation_id"] == 1
    assert analysis["version_no"] == 2
    assert analysis["event_id"] == 7  # newest FakeClient event for regulation 1

    # StubLLM rule extraction from the fixture texts
    assert analysis["effective_date"] == "2026-11-01"
    assert analysis["risk_level"] == "HIGH"
    assert analysis["summary"]
    assert analysis["key_changes"] and all(
        isinstance(k, str) for k in analysis["key_changes"])
    assert analysis["affected_entities"] and all(
        isinstance(k, str) for k in analysis["affected_entities"])
    assert analysis["required_actions"] and all(
        isinstance(k, str) for k in analysis["required_actions"])
    assert analysis["generated_at"].endswith("Z")

    validate_analysis(analysis)  # raises AnalysisError on any contract drift


def test_relevance_levels_are_scored_per_company(processed_storage,
                                                 fake_client):
    result = run_analysis(regulation_id=1, version_no=2, emit=False,
                          client=fake_client)
    relevance = result.analysis["relevance"]
    by_company = {entry["company_id"]: entry for entry in relevance}

    assert set(by_company) == {1, 2}
    assert by_company[1]["level"] == "HIGH"   # Banking/NBFC/Fintech vs RBI circular
    assert by_company[2]["level"] == "NONE"   # Textiles vs RBI circular
    for entry in relevance:
        assert set(entry) == {"company_id", "company_name", "level", "rationale"}
        assert entry["level"] in {"HIGH", "MEDIUM", "LOW", "NONE"}
        assert entry["rationale"]


def test_old_version_missing_flag(processed_storage_new_only, fake_client):
    result = run_analysis(regulation_id=2, version_no=2, emit=False,
                          client=fake_client)
    analysis = result.analysis
    assert analysis["old_version_missing"] is True
    validate_analysis(analysis)


def test_old_version_present_has_no_flag(processed_storage, fake_client):
    result = run_analysis(regulation_id=1, version_no=2, emit=False,
                          client=fake_client)
    assert "old_version_missing" not in result.analysis


def test_analysis_written_to_storage(processed_storage, fake_client, isolated_env):
    run_analysis(regulation_id=1, version_no=2, emit=False, client=fake_client)
    path = isolated_env / "analysis" / "1" / "v2.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in CONTRACT_KEYS:
        assert key in payload


def test_vector_indexing_reports_chunks(processed_storage, fake_client):
    result = run_analysis(regulation_id=1, version_no=2, emit=False,
                          client=fake_client)
    assert result.indexing["ok"] is True
    assert result.indexing["chunks"] > 0
    assert result.indexing["backend"] in {"chroma", "jsonl"}


def test_missing_content_raises_analysis_error(isolated_env, fake_client):
    with pytest.raises(AnalysisError):
        run_analysis(regulation_id=404, version_no=3, emit=False,
                     client=fake_client)
