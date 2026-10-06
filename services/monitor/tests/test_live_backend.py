"""Live integration check against the running backend (PLAN.md §1.2).

Skips automatically when http://localhost:8080 is unreachable so the suite
stays green offline; when the backend is up it sends exactly one signed
self-test event with a clearly test URL and expects HTTP 202.
"""

from __future__ import annotations

import json
import os

import pytest

from monitor.config import DEFAULT_API_BASE, DEFAULT_WEBHOOK_SECRET
from monitor.notifier import SIGNATURE_HEADER, build_payload, notify, sign, canonical_body
from monitor.retriever import utc_now_iso

API_BASE = os.environ.get("API_BASE", DEFAULT_API_BASE).rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", DEFAULT_WEBHOOK_SECRET)
TEST_URL = "https://www.rbi.org.in/test-monitor-selftest.html"


def _backend_reachable() -> bool:
    import httpx

    try:
        response = httpx.get(f"{API_BASE}/actuator/health", timeout=3.0)
    except Exception:
        return False
    return response.status_code == 200


@pytest.mark.skipif(not _backend_reachable(), reason=f"backend not reachable at {API_BASE}")
def test_live_webhook_accepts_signed_event() -> None:
    """One real signed delivery: expect HTTP 202 + eventId acknowledgement."""
    payload = build_payload(
        url=TEST_URL,
        title="Monitor self-test (safe to delete)",
        source_code="RBI",
        content="regtrack monitor self-test — signed webhook round-trip probe.",
        timestamp=utc_now_iso(),
    )

    result = notify(
        payload,
        endpoint=f"{API_BASE}/api/webhooks/changedetection",
        secret=WEBHOOK_SECRET,
        timeout=10.0,
    )

    assert result.error is None, result.error
    assert result.status_code == 202, (result.status_code, result.response_text)
    assert result.headers[SIGNATURE_HEADER] == sign(canonical_body(payload), WEBHOOK_SECRET)

    body = json.loads(result.response_text or "{}")
    assert "eventId" in body
    assert body.get("status") in {"RECEIVED", "PENDING", "NEW"}
    assert body.get("regulationId") is not None
