"""Self-test: two different fixture HTML files → change detected → signed payload.

Covers the Definition of Done for the monitor role:

* snapshot persistence and sha256 change detection via ``MonitorRunner``
* no-change on identical content
* unified diff written next to the snapshots
* payload exactly matches the PLAN.md §1.2 contract and is ASCII-safe
* ``X-Webhook-Signature`` equals ``sha256=<hex hmac-sha256(raw_body, secret)>``
* ``--dry-run`` behaviour: signed headers, nothing sent
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest

from monitor.config import Settings, SourceConfig
from monitor.notifier import (
    SIGNATURE_HEADER,
    NotifyResult,
    build_payload,
    canonical_body,
    notify,
    signed_headers,
)
from monitor.retriever import FetchResult, extract_text, fetch, utc_now_iso
from monitor.runner import MonitorRunner
from monitor.snapshots import SnapshotStore, sha256_text

FIXTURES = Path(__file__).parent / "fixtures"
SECRET = "unit-test-webhook-secret"
TEST_URL = "https://www.rbi.org.in/Scripts/BS_ViewMasNotifications.aspx"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings pointing at a temporary snapshot root."""
    return Settings(
        api_base="http://localhost:8080",
        webhook_secret=SECRET,
        storage_dir=tmp_path / "snapshots",
        sources_path=tmp_path / "sources.yaml",
        notify_initial=True,
        payload_mode="text",
        timeout=5.0,
        user_agent="regtrack-monitor-tests/1.0",
    )


@pytest.fixture
def source() -> SourceConfig:
    """RBI source matching the seeded regulation_sources row."""
    return SourceConfig(
        code="RBI",
        name="Reserve Bank of India",
        base_url="https://www.rbi.org.in",
        watch_url=TEST_URL,
    )


def fixture_fetch(name: str, url: str) -> FetchResult:
    """Build a :class:`FetchResult` from a fixture HTML file."""
    html = (FIXTURES / name).read_text(encoding="utf-8")
    title, text = extract_text(html)
    return FetchResult(
        url=url,
        engine="file",
        html=html,
        text=text,
        title=title,
        fetched_at=utc_now_iso(),
        status_code=200,
    )


def recording_notifier() -> tuple[list[dict[str, Any]], Any]:
    """Fake notifier capturing raw bodies and signed headers instead of POSTing."""
    calls: list[dict[str, Any]] = []

    def fake(payload: dict[str, str], *, endpoint: str, secret: str,
             dry_run: bool = False, timeout: float = 15.0) -> NotifyResult:
        raw = canonical_body(payload)
        headers = signed_headers(raw, secret)
        calls.append({"payload": payload, "raw": raw, "headers": headers, "dry_run": dry_run})
        return NotifyResult(
            sent=not dry_run,
            dry_run=dry_run,
            endpoint=endpoint,
            headers=headers,
            status_code=None if dry_run else 202,
            response_text=None if dry_run else '{"eventId":1}',
        )

    return calls, fake


def expected_signature(raw_body: bytes, secret: str) -> str:
    """Reference HMAC computed independently of production code."""
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_two_fixture_files_detect_change_and_sign(settings: Settings, source: SourceConfig) -> None:
    """v1 → baseline, v1 again → no change, v2 → change + correct HMAC signature."""
    calls, fake = recording_notifier()
    state = {"fixture": "page_v1.html"}
    runner = MonitorRunner(
        settings,
        [source],
        fetcher=lambda _source: fixture_fetch(state["fixture"], source.watch_url),
        notifier=fake,
    )

    first = runner.run_once()
    assert first.checked == 1
    assert first.changed == [TEST_URL]
    assert first.outcomes[0].signature == expected_signature(calls[0]["raw"], SECRET)

    second = runner.run_once()
    assert second.checked == 1
    assert second.changed == []
    assert len(calls) == 1

    state["fixture"] = "page_v2.html"
    third = runner.run_once()
    assert third.changed == [TEST_URL]
    assert len(calls) == 2

    call = calls[-1]
    raw: bytes = call["raw"]
    ascii_body = raw.decode("ascii")
    payload = json.loads(ascii_body)

    assert set(payload) == {"url", "title", "source_code", "content", "timestamp"}
    assert payload["url"] == TEST_URL
    assert payload["source_code"] == "RBI"
    assert "Master Directions" in payload["title"]
    assert "Tokenisation of Payment Cards" in payload["content"]
    assert payload["timestamp"].endswith("Z")

    assert call["headers"][SIGNATURE_HEADER] == expected_signature(raw, SECRET)
    assert call["headers"][SIGNATURE_HEADER].startswith("sha256=")

    code_dir = settings.storage_dir / "RBI"
    assert (code_dir / "latest.txt").exists()
    assert (code_dir / "latest.html").exists()
    assert (code_dir / "latest.meta.json").exists()
    assert len(list((code_dir / "history").glob("*.txt"))) == 2

    diffs = sorted((code_dir / "diffs").glob("*.diff"))
    assert len(diffs) == 2
    diff_text = diffs[-1].read_text(encoding="utf-8")
    assert "Tokenisation of Payment Cards" in diff_text
    assert "+NEW:" in diff_text

    latest_text = (code_dir / "latest.txt").read_text(encoding="utf-8")
    assert sha256_text(latest_text) == json.loads(
        (code_dir / "latest.meta.json").read_text(encoding="utf-8")
    )["sha256"]


def test_payload_is_ascii_safe_for_non_ascii_content() -> None:
    """ensure_ascii serialisation keeps the raw body pure ASCII and lossless."""
    payload = build_payload(
        url="https://www.sebi.gov.in/test.html",
        title="कोष – ₹1,000 penalty",
        source_code="SEBI",
        content="Fine of ₹1,000,000 levied — “café” naïve.",
        timestamp="2026-10-03T12:00:00Z",
    )
    raw = canonical_body(payload)
    assert raw.decode("ascii")
    assert json.loads(raw.decode("utf-8")) == payload


def test_dry_run_signs_but_does_not_send(settings: Settings, source: SourceConfig) -> None:
    """--dry-run path: valid signature produced, notifier marks nothing sent."""
    calls, fake = recording_notifier()
    runner = MonitorRunner(
        settings,
        [source],
        fetcher=lambda _source: fixture_fetch("page_v1.html", source.watch_url),
        notifier=fake,
    )
    summary = runner.run_once(dry_run=True)

    assert summary.changed == [TEST_URL]
    assert summary.dry_run is True
    outcome = summary.outcomes[0]
    assert outcome.notified is False
    assert outcome.signature == expected_signature(calls[0]["raw"], SECRET)
    assert calls[0]["dry_run"] is True

    direct = notify(
        {"url": "https://example.org/x", "title": "t", "source_code": "RBI",
         "content": "c", "timestamp": "2026-10-03T12:00:00Z"},
        endpoint="http://localhost:8080/api/webhooks/changedetection",
        secret=SECRET,
        dry_run=True,
    )
    assert direct.sent is False
    assert direct.headers[SIGNATURE_HEADER] == expected_signature(
        canonical_body({"url": "https://example.org/x", "title": "t", "source_code": "RBI",
                        "content": "c", "timestamp": "2026-10-03T12:00:00Z"}),
        SECRET,
    )


def test_initial_snapshot_can_skip_notification(tmp_path: Path, source: SourceConfig) -> None:
    """MONITOR_NOTIFY_INITIAL=false stores the baseline without an event."""
    settings = Settings(
        api_base="http://localhost:8080",
        webhook_secret=SECRET,
        storage_dir=tmp_path / "snapshots",
        sources_path=tmp_path / "sources.yaml",
        notify_initial=False,
        payload_mode="text",
        timeout=5.0,
        user_agent="regtrack-monitor-tests/1.0",
    )
    calls, fake = recording_notifier()
    runner = MonitorRunner(
        settings,
        [source],
        fetcher=lambda _source: fixture_fetch("page_v1.html", source.watch_url),
        notifier=fake,
    )
    summary = runner.run_once()
    assert summary.changed == []
    assert calls == []
    assert (settings.storage_dir / "RBI" / "latest.txt").exists()


def test_file_engine_fetch(tmp_path: Path) -> None:
    """file:// URLs are readable without network (offline fixtures)."""
    local = tmp_path / "page.html"
    local.write_text((FIXTURES / "page_v1.html").read_text(encoding="utf-8"), encoding="utf-8")
    result = fetch(local.as_uri())
    assert result.engine == "file"
    assert result.title.startswith("Master Directions")
    assert "Interest Rate on Deposits" in result.text


def test_snapshot_store_roundtrip(tmp_path: Path, source: SourceConfig) -> None:
    """Snapshot persistence keeps text, html, meta and history in sync."""
    store = SnapshotStore(tmp_path / "snapshots")
    assert store.load_latest("RBI") is None

    fetched = fixture_fetch("page_v1.html", source.watch_url)
    store.save("RBI", fetched, sha256_text(fetched.text))
    stored = store.load_latest("RBI")
    assert stored is not None
    assert stored.text == fetched.text
    assert stored.meta["url"] == source.watch_url
    assert stored.meta["sha256"] == sha256_text(fetched.text)
    assert len(list((tmp_path / "snapshots" / "RBI" / "history").glob("*.txt"))) == 1
