"""Shared fixtures and helpers for the regtrack QA test suite.

All tests use random (uuid-derived) data so the suite is re-runnable against a
long-lived database. No test writes outside tests/, docs/ and the e2e script.
"""

import hashlib
import hmac
import json
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("API_BASE", "http://localhost:8080").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dev-webhook-shared-secret-please-change")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@regtrack.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")

PROJECT_ROOT = r"D:\AI_Hack"

WEBHOOK_PATH = "/api/webhooks/changedetection"


def uid(n: int = 10) -> str:
    """Random unique fragment for test data."""
    return uuid.uuid4().hex[:n]


def sign_body(raw: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """X-Webhook-Signature value over the raw request body (PLAN §1.2)."""
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return "sha256=" + digest


def webhook_body(url: str, content: str, title: str = "QA Test Circular",
                 source_code: str = "RBI") -> bytes:
    """ASCII-safe raw JSON body for the changedetection webhook."""
    payload = {
        "url": url,
        "title": title,
        "source_code": source_code,
        "content": content,
        "timestamp": "2026-10-03T12:00:00Z",
    }
    return json.dumps(payload).encode("utf-8")


def post_webhook(base_url: str, raw: bytes, signature: str | None = None,
                 token: str | None = None, extra_headers: dict | None = None):
    """POST the webhook, returning the requests.Response (never raises on 4xx)."""
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Webhook-Signature"] = signature
    if token is not None:
        headers["X-Webhook-Token"] = token
    if extra_headers:
        headers.update(extra_headers)
    try:
        return requests.post(base_url + WEBHOOK_PATH, data=raw, headers=headers, timeout=30)
    except requests.RequestException as exc:  # pragma: no cover - environment failure
        pytest.fail(f"backend unreachable at {base_url}: {exc}")


def request(method: str, url: str, **kwargs):
    """requests wrapper that turns connection errors into readable failures."""
    kwargs.setdefault("timeout", 30)
    try:
        return requests.request(method, url, **kwargs)
    except requests.RequestException as exc:  # pragma: no cover - environment failure
        pytest.fail(f"backend unreachable ({method} {url}): {exc}")


@pytest.fixture(scope="session")
def base_url() -> str:
    r = request("GET", BASE_URL + "/actuator/health")
    if r.status_code != 200:
        pytest.fail(f"backend health check failed: HTTP {r.status_code} {r.text[:200]}")
    return BASE_URL


@pytest.fixture(scope="session")
def admin_token(base_url) -> str:
    r = request("POST", base_url + "/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.fail(f"admin login failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["token"]


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_officer(base_url):
    """Factory: registers a fresh COMPLIANCE_OFFICER with a unique company."""

    def _make(prefix: str = "officer") -> dict:
        run = uid()
        email = f"{prefix}+{run}@qa.test"
        company_name = f"QA Co {run} Ltd"
        r = request("POST", base_url + "/api/auth/register", json={
            "email": email,
            "password": "Passw0rd!23",
            "fullName": "QA Compliance Officer",
            "companyName": company_name,
            "industry": "Banking & NBFC",
        })
        if r.status_code != 201:
            pytest.fail(f"register failed: HTTP {r.status_code} {r.text[:300]}")
        data = r.json()
        return {
            "email": email,
            "token": data["token"],
            "companyId": data["user"]["companyId"],
            "companyName": company_name,
        }

    return _make


@pytest.fixture
def change_event(base_url, admin_token):
    """Factory: creates a unique regulation + change event via the signed webhook."""

    def _make(content: str | None = None) -> dict:
        run = uid()
        url = f"https://www.rbi.org.in/notifications/2026/qa-{run}.html"
        raw = webhook_body(url, content or f"<html><body>QA circular body {run}</body></html>",
                           title=f"QA Circular {run}")
        r = post_webhook(base_url, raw, signature=sign_body(raw))
        if r.status_code != 202:
            pytest.fail(f"webhook failed: HTTP {r.status_code} {r.text[:300]}")
        ack = r.json()
        ack["url"] = url
        return ack

    return _make
