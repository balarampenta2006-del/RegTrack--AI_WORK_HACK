"""Webhook security & regulation versioning tests (PLAN §1.2).

Covers: missing signature -> 401, wrong HMAC -> 401, valid HMAC over the raw
body -> 202 + ack shape, static token header, replay/tamper rejection,
content-hash dedupe (same content twice => no second version), and version
creation on content change.
"""

import uuid

from conftest import bearer, post_webhook, request, sign_body, uid, webhook_body


def unique_url() -> str:
    return f"https://www.rbi.org.in/notifications/2026/qa-{uid()}.html"


# --------------------------------------------------------------------------
# Signature enforcement
# --------------------------------------------------------------------------

def test_webhook_without_signature_rejected(base_url):
    raw = webhook_body(unique_url(), "<html><body>unsigned body</body></html>")
    r = post_webhook(base_url, raw)
    assert r.status_code == 401


def test_webhook_with_wrong_hmac_rejected(base_url):
    raw = webhook_body(unique_url(), "<html><body>wrongly signed body</body></html>")
    r = post_webhook(base_url, raw, signature="sha256=" + "0" * 64)
    assert r.status_code == 401


def test_webhook_with_hmac_of_tampered_body_rejected(base_url):
    original = webhook_body(unique_url(), "<html><body>original</body></html>")
    signature = sign_body(original)  # signature computed over a different body
    tampered = webhook_body(unique_url(), "<html><body>attacker content</body></html>")
    r = post_webhook(base_url, tampered, signature=signature)
    assert r.status_code == 401


def test_webhook_with_garbage_signature_rejected(base_url):
    raw = webhook_body(unique_url(), "<html><body>garbage sig</body></html>")
    r = post_webhook(base_url, raw, signature="sha256=zzzz")
    assert r.status_code == 401


def test_webhook_with_empty_token_rejected(base_url):
    raw = webhook_body(unique_url(), "<html><body>empty token</body></html>")
    r = post_webhook(base_url, raw, token="")
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Accepted calls + ack contract (PLAN §1.2)
# --------------------------------------------------------------------------

def test_webhook_valid_hmac_accepted(base_url):
    url = unique_url()
    raw = webhook_body(url, f"<html><body>QA valid signature body {uid()}</body></html>")
    r = post_webhook(base_url, raw, signature=sign_body(raw))
    assert r.status_code == 202, r.text
    ack = r.json()
    for key in ("eventId", "status", "regulationId", "newVersionId", "receivedAt"):
        assert key in ack, f"ack missing {key}: {ack}"
    assert ack["regulationId"]
    assert ack["newVersionId"]
    assert ack["status"] == "RECEIVED"


def test_webhook_valid_hmac_signature_is_case_insensitive(base_url):
    raw = webhook_body(unique_url(), f"<html><body>uppercase sig {uid()}</body></html>")
    signed = sign_body(raw)  # sha256=<lower-hex>
    r = post_webhook(base_url, raw, signature="sha256=" + signed.split("=", 1)[1].upper())
    assert r.status_code == 202, r.text


def test_webhook_static_token_accepted(base_url):
    from conftest import WEBHOOK_SECRET
    raw = webhook_body(unique_url(), f"<html><body>token auth {uid()}</body></html>")
    r = post_webhook(base_url, raw, token=WEBHOOK_SECRET)
    assert r.status_code == 202, r.text


def test_webhook_wrong_static_token_rejected(base_url):
    raw = webhook_body(unique_url(), f"<html><body>wrong token {uid()}</body></html>")
    r = post_webhook(base_url, raw, token="not-the-shared-secret")
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Version dedupe + versioning semantics
# --------------------------------------------------------------------------

def test_same_content_twice_creates_no_second_version(base_url, admin_token):
    url = unique_url()
    raw = webhook_body(url, f"<html><body>Version 1 text {uid()}</body></html>")

    r1 = post_webhook(base_url, raw, signature=sign_body(raw))
    assert r1.status_code == 202, r1.text
    ack1 = r1.json()
    assert ack1["newVersionId"]

    r2 = post_webhook(base_url, raw, signature=sign_body(raw))
    assert r2.status_code == 202, r2.text
    ack2 = r2.json()
    assert ack2["regulationId"] == ack1["regulationId"]
    # non_null JSON serialization: the omitted key means "no new version"
    assert ack2.get("newVersionId") is None, (
        "identical content must not produce a new version (PLAN §1.2 dedupe)")

    r = request("GET",
                f"{base_url}/api/regulations/{ack1['regulationId']}/versions",
                headers=bearer(admin_token))
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_changed_content_creates_second_version(base_url, admin_token):
    url = unique_url()
    run = uid()
    raw_v1 = webhook_body(url, f"<html><body>Version 1 of circular {run}</body></html>")
    raw_v2 = webhook_body(url, f"<html><body>Version 2 of circular {run}</body></html>")

    ack1 = post_webhook(base_url, raw_v1, signature=sign_body(raw_v1)).json()
    ack2 = post_webhook(base_url, raw_v2, signature=sign_body(raw_v2)).json()

    assert ack1["regulationId"] == ack2["regulationId"]
    assert ack2["newVersionId"]
    assert ack2["newVersionId"] != ack1["newVersionId"]

    r = request("GET",
                f"{base_url}/api/regulations/{ack2['regulationId']}/versions",
                headers=bearer(admin_token))
    assert r.status_code == 200
    versions = r.json()
    assert len(versions) == 2

    r = request("GET",
                f"{base_url}/api/regulations/{ack2['regulationId']}/versions/"
                f"{ack2['newVersionId']}",
                headers=bearer(admin_token))
    assert r.status_code == 200
    assert "Version 2" in r.json()["content"]


def test_webhook_requires_url_field(base_url):
    import json as _json
    raw = _json.dumps({"title": "no url", "content": "x"}).encode()
    r = post_webhook(base_url, raw, signature=sign_body(raw))
    assert r.status_code == 400
