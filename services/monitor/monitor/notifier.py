"""Webhook notifier with HMAC-SHA256 request signing (PLAN.md §1.2).

Payload::

    {"url": "...", "title": "...", "source_code": "RBI",
     "content": "...", "timestamp": "2026-10-03T12:00:00Z"}

Signed with header::

    X-Webhook-Signature: sha256=<hex hmac-sha256(raw_body, WEBHOOK_SECRET)>

The raw body is ASCII-safe JSON (``ensure_ascii=True``); the signature is
computed over the exact bytes that are transmitted.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field

log = logging.getLogger("monitor.notifier")

SIGNATURE_HEADER = "X-Webhook-Signature"
TOKEN_HEADER = "X-Webhook-Token"
SIGNATURE_PREFIX = "sha256="

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is pre-installed
    httpx = None  # type: ignore[assignment]

try:
    import requests
except ImportError:  # pragma: no cover - requests is pre-installed
    requests = None  # type: ignore[assignment]


@dataclass(frozen=True)
class NotifyResult:
    """Outcome of one webhook delivery attempt."""

    sent: bool
    dry_run: bool
    endpoint: str
    headers: dict[str, str] = field(default_factory=dict)
    status_code: int | None = None
    response_text: str | None = None
    error: str | None = None


def build_payload(
    url: str,
    title: str,
    source_code: str,
    content: str,
    timestamp: str,
) -> dict[str, str]:
    """Build the change-detection webhook payload (PLAN.md §1.2).

    Args:
        url: Changed page URL.
        title: Page or regulation title.
        source_code: Seeded source code (``MCA``/``RBI``/``SEBI``).
        content: Clean text (or raw HTML) of the new snapshot.
        timestamp: ISO-8601 UTC timestamp ending in ``Z``.

    Returns:
        Payload mapping with exactly the contract keys.
    """
    return {
        "url": url,
        "title": title,
        "source_code": source_code,
        "content": content,
        "timestamp": timestamp,
    }


def canonical_body(payload: dict[str, str]) -> bytes:
    """Serialise ``payload`` to ASCII-safe JSON bytes (the signed raw body)."""
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def sign(raw_body: bytes, secret: str) -> str:
    """Return ``sha256=<hex hmac-sha256(raw_body, secret)>``."""
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def signed_headers(raw_body: bytes, secret: str) -> dict[str, str]:
    """Headers for a signed webhook delivery (signature over exact bytes)."""
    return {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "regtrack-monitor/1.0",
        SIGNATURE_HEADER: sign(raw_body, secret),
    }


def notify(
    payload: dict[str, str],
    *,
    endpoint: str,
    secret: str,
    dry_run: bool = False,
    timeout: float = 15.0,
) -> NotifyResult:
    """POST a signed change event to the backend webhook.

    Args:
        payload: Contract payload (see :func:`build_payload`).
        endpoint: Full webhook URL, e.g. ``{API_BASE}/api/webhooks/changedetection``.
        secret: Shared ``WEBHOOK_SECRET``.
        dry_run: When True, compute and return signed headers without sending.
        timeout: POST timeout in seconds.

    Returns:
        :class:`NotifyResult`; ``sent=True`` only on HTTP 202.
    """
    raw_body = canonical_body(payload)
    headers = signed_headers(raw_body, secret)
    signature = headers[SIGNATURE_HEADER]

    if dry_run:
        log.info("[dry-run] would POST %s %s (%d bytes)", endpoint, signature, len(raw_body))
        return NotifyResult(
            sent=False,
            dry_run=True,
            endpoint=endpoint,
            headers=headers,
            status_code=None,
            response_text=None,
        )

    try:
        status_code, response_text = _post(endpoint, raw_body, headers, timeout)
    except Exception as exc:
        log.error("webhook delivery failed for %s: %s", payload.get("url"), exc)
        return NotifyResult(
            sent=False,
            dry_run=False,
            endpoint=endpoint,
            headers=headers,
            error=str(exc),
        )

    sent = status_code == 202
    if not sent:
        log.error("webhook rejected with HTTP %s: %s", status_code, (response_text or "")[:300])
    return NotifyResult(
        sent=sent,
        dry_run=False,
        endpoint=endpoint,
        headers=headers,
        status_code=status_code,
        response_text=response_text,
    )


def _post(endpoint: str, raw_body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    """Send raw bytes with httpx (primary) or requests (fallback)."""
    if httpx is not None:
        response = httpx.post(endpoint, content=raw_body, headers=headers, timeout=timeout)
        return response.status_code, response.text
    if requests is not None:
        response = requests.post(endpoint, data=raw_body, headers=headers, timeout=timeout)
        return response.status_code, response.text
    raise RuntimeError("neither httpx nor requests is available")
