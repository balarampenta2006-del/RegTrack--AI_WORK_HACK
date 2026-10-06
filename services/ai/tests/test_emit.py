"""Alert emission tests against a fake backend client (no network)."""

import pytest

from ai.analyze import run_analysis
from ai.client import BackendError
from ai.emit import emit_alerts, resolve_event_id

ALERT_KEYS = {"companyId", "changeEventId", "relevance", "summary",
              "affectedAreas", "effectiveDate", "requiredAction",
              "emailRecipients"}


def _analysis(relevance, regulation_id=1):
    return {
        "regulation_id": regulation_id,
        "version_no": 2,
        "event_id": None,
        "analysis_mode": "stub",
        "model": "stub-rules",
        "summary": "Amended RBI circular on digital lending.",
        "key_changes": ["Video KYC made mandatory"],
        "affected_entities": ["NBFCs"],
        "effective_date": "2026-11-01",
        "required_actions": ["Update KYC policy before 2026-11-01"],
        "risk_level": "HIGH",
        "relevance": relevance,
        "generated_at": "2026-10-03T12:00:00Z",
    }


HIGH = {"company_id": 1, "company_name": "Acme Fintech Ltd", "level": "HIGH",
        "rationale": "sector + regulator match"}
NONE = {"company_id": 2, "company_name": "Textiles Inc", "level": "NONE",
        "rationale": "no overlap"}


def test_emit_creates_one_alert_per_non_none_entry(fake_client):
    report = emit_alerts(_analysis([HIGH, NONE]), client=fake_client)

    assert report["status"] == "verified"
    assert report["event_id"] == 7  # FakeClient newest event for regulation 1
    assert len(fake_client.created_alerts) == 1

    payload = fake_client.created_alerts[0]
    assert set(payload) == ALERT_KEYS
    assert payload["companyId"] == 1
    assert payload["changeEventId"] == 7
    assert payload["relevance"] == "HIGH"
    assert payload["effectiveDate"] == "2026-11-01"
    assert payload["emailRecipients"] == "cso@acme.test"
    assert payload["summary"]
    assert payload["requiredAction"]


def test_emit_skips_when_all_none(fake_client):
    report = emit_alerts(_analysis([NONE]), client=fake_client)
    assert report["status"] == "skipped"
    assert fake_client.created_alerts == []


def test_emit_deferred_when_no_event_matches(fake_client):
    report = emit_alerts(_analysis([HIGH], regulation_id=99), client=fake_client)
    assert report["status"] == "deferred"
    assert report["event_id"] is None
    assert "no change event" in report["reason"]
    assert fake_client.created_alerts == []


def test_emit_uses_provided_event_id(fake_client):
    report = emit_alerts(_analysis([HIGH]), event_id=42, client=fake_client)
    assert report["status"] == "verified"
    assert report["event_id"] == 42
    assert fake_client.created_alerts[0]["changeEventId"] == 42


def test_emit_deferred_when_backend_write_fails(fake_client):
    def _fail(payload):
        raise BackendError("POST /api/alerts -> HTTP 500")

    fake_client.create_alert = _fail
    report = emit_alerts(_analysis([HIGH]), client=fake_client)
    assert report["status"] == "deferred"
    assert report["deferred"]


def test_resolve_event_id_prefers_argument(fake_client):
    event_id, note = resolve_event_id(fake_client, 1, event_id=5)
    assert event_id == 5
    assert note == "provided"


def test_pipeline_emits_alerts(processed_storage, fake_client):
    result = run_analysis(regulation_id=1, version_no=2, emit=True,
                          client=fake_client)
    assert result.emission["status"] == "verified"
    assert len(fake_client.created_alerts) == 1
    payload = fake_client.created_alerts[0]
    assert set(payload) == ALERT_KEYS
    assert payload["relevance"] == "HIGH"
    assert payload["changeEventId"] == 7
