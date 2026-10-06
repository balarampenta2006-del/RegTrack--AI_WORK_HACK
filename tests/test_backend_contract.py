"""Live backend API contract tests (PLAN §1.1).

Covers: auth round-trip, RBAC matrix, error-shape validation, alert scoping.
Every test generates its own random data so the suite is re-runnable.
"""

import uuid

import pytest
import requests

from conftest import ADMIN_EMAIL, bearer, request

FULL_ERROR_KEYS = {"timestamp", "status", "error", "message"}


# --------------------------------------------------------------------------
# Health / auth
# --------------------------------------------------------------------------

def test_health_endpoint_public(base_url):
    r = request("GET", base_url + "/actuator/health")
    assert r.status_code == 200
    assert r.json()["status"] == "UP"


def test_register_login_me_roundtrip(base_url, make_officer):
    officer = make_officer()

    r = request("POST", base_url + "/api/auth/login",
                json={"email": officer["email"], "password": "Passw0rd!23"})
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["expiresInSeconds"] > 0
    user = body["user"]
    assert user["email"] == officer["email"]
    assert user["role"] == "COMPLIANCE_OFFICER"
    assert user["companyId"] == officer["companyId"]
    assert user["companyName"] == officer["companyName"]

    r = request("GET", base_url + "/api/me", headers=bearer(body["token"]))
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == officer["email"]
    assert me["role"] == "COMPLIANCE_OFFICER"
    assert me["companyId"] == officer["companyId"]


def test_duplicate_registration_conflict(base_url, make_officer):
    officer = make_officer()
    r = request("POST", base_url + "/api/auth/register", json={
        "email": officer["email"],
        "password": "Passw0rd!23",
        "fullName": "Duplicate",
    })
    assert r.status_code == 409


def test_wrong_password_unauthorized(base_url):
    r = request("POST", base_url + "/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": "definitely-not-the-password"})
    assert r.status_code == 401


def test_unauthenticated_me_unauthorized(base_url):
    r = request("GET", base_url + "/api/me")
    assert r.status_code == 401


def test_invalid_bearer_token_unauthorized(base_url):
    r = request("GET", base_url + "/api/me", headers=bearer("not.a.real.jwt"))
    assert r.status_code == 401


# --------------------------------------------------------------------------
# RBAC matrix (PLAN §1.1)
# --------------------------------------------------------------------------

def test_rbac_officer_cannot_create_source(base_url, make_officer):
    officer = make_officer()
    r = request("POST", base_url + "/api/sources",
                json={"code": "QA" + uuid.uuid4().hex[:8], "name": "QA Source"},
                headers=bearer(officer["token"]))
    assert r.status_code == 403


def test_rbac_officer_cannot_read_audit(base_url, make_officer):
    officer = make_officer()
    r = request("GET", base_url + "/api/audit", headers=bearer(officer["token"]))
    assert r.status_code == 403


def test_rbac_admin_reads_audit(base_url, admin_token):
    r = request("GET", base_url + "/api/audit", headers=bearer(admin_token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_rbac_admin_reads_sources(base_url, admin_token):
    r = request("GET", base_url + "/api/sources", headers=bearer(admin_token))
    assert r.status_code == 200
    codes = {s["code"] for s in r.json()}
    assert {"MCA", "RBI", "SEBI"} <= codes


def test_rbac_officer_reads_sources(base_url, make_officer):
    officer = make_officer()
    r = request("GET", base_url + "/api/sources", headers=bearer(officer["token"]))
    assert r.status_code == 200


def test_rbac_admin_creates_source(base_url, admin_token):
    code = "QA" + uuid.uuid4().hex[:8]
    r = request("POST", base_url + "/api/sources", json={
        "code": code,
        "name": "QA Test Department " + code,
        "agency": "QA",
        "baseUrl": "https://qa.example.gov.in",
        "watchUrl": "https://qa.example.gov.in/notices",
        "active": True,
    }, headers=bearer(admin_token))
    assert r.status_code == 201
    assert r.json()["code"] == code.upper()  # backend normalises codes to upper-case


def test_rbac_anonymous_source_write_blocked(base_url):
    r = request("POST", base_url + "/api/sources", json={"code": "QA" + uuid.uuid4().hex[:6],
                                                         "name": "Anon"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Error shape (PLAN §1.1: {timestamp,status,error,message[,fields]})
# --------------------------------------------------------------------------

def assert_full_error_shape(resp, expected_status):
    body = resp.json()
    missing = FULL_ERROR_KEYS - set(body)
    assert not missing, f"missing keys {missing} in {body}"
    assert body["status"] == expected_status
    assert isinstance(body["message"], str) and body["message"]
    assert body["timestamp"]
    return body


def test_error_shape_not_found(base_url, admin_token):
    r = request("GET", base_url + "/api/companies/99999999",
                headers=bearer(admin_token))
    assert r.status_code == 404
    assert_full_error_shape(r, 404)


def test_error_shape_validation_400(base_url):
    r = request("POST", base_url + "/api/auth/register", json={})
    assert r.status_code == 400
    body = assert_full_error_shape(r, 400)
    assert "fields" in body and body["fields"]


def test_error_shape_unauthorized_from_auth_handler(base_url):
    r = request("POST", base_url + "/api/auth/login",
                json={"email": "ghost-" + uuid.uuid4().hex[:8] + "@qa.test",
                      "password": "wrong-password"})
    assert r.status_code == 401
    assert_full_error_shape(r, 401)


def test_error_shape_conflict_409(base_url, make_officer):
    officer = make_officer()
    r = request("POST", base_url + "/api/auth/register", json={
        "email": officer["email"], "password": "Passw0rd!23", "fullName": "Dup"})
    assert r.status_code == 409
    assert_full_error_shape(r, 409)


@pytest.mark.xfail(reason="KNOWN GAP: SecurityConfig entry-point/denied handlers emit "
                          "{error,message} only - missing timestamp/status "
                          "(see docs/known-issues.md #1)", strict=False)
def test_error_shape_security_chain_401(base_url):
    r = request("GET", base_url + "/api/me")
    assert r.status_code == 401
    assert_full_error_shape(r, 401)


@pytest.mark.xfail(reason="KNOWN GAP: SecurityConfig entry-point/denied handlers emit "
                          "{error,message} only - missing timestamp/status "
                          "(see docs/known-issues.md #1)", strict=False)
def test_error_shape_security_chain_403(base_url, make_officer):
    officer = make_officer()
    r = request("POST", base_url + "/api/sources",
                json={"code": "QA" + uuid.uuid4().hex[:6], "name": "Nope"},
                headers=bearer(officer["token"]))
    assert r.status_code == 403
    assert_full_error_shape(r, 403)


# --------------------------------------------------------------------------
# Alert scoping (PLAN §1.1: officer = own company, ADMIN = all)
# --------------------------------------------------------------------------

def test_alert_scoping_officer_sees_only_own_company(base_url, admin_token,
                                                     make_officer, change_event):
    officer_a = make_officer("a")
    officer_b = make_officer("b")
    event = change_event()

    r = request("POST", base_url + "/api/alerts", json={
        "companyId": officer_a["companyId"],
        "changeEventId": event["eventId"],
        "relevance": "HIGH",
        "summary": "QA scoping alert for company A",
        "affectedAreas": "Testing",
        "effectiveDate": "2026-12-01",
        "requiredAction": "Ignore - QA test alert.",
        "emailRecipients": officer_a["email"],
    }, headers=bearer(officer_a["token"]))
    assert r.status_code == 201
    alert_id = r.json()["id"]

    # officer A sees it
    r = request("GET", base_url + "/api/alerts", headers=bearer(officer_a["token"]))
    assert r.status_code == 200
    a_ids = {a["id"] for a in r.json()}
    assert alert_id in a_ids
    assert {a["companyId"] for a in r.json()} == {officer_a["companyId"]}

    # officer B must not see company A's alert
    r = request("GET", base_url + "/api/alerts", headers=bearer(officer_b["token"]))
    assert r.status_code == 200
    b_alerts = r.json()
    assert alert_id not in {a["id"] for a in b_alerts}
    assert all(a["companyId"] == officer_b["companyId"] for a in b_alerts)

    # admin sees everything
    r = request("GET", base_url + "/api/alerts", headers=bearer(admin_token))
    assert r.status_code == 200
    assert alert_id in {a["id"] for a in r.json()}


def test_alert_cannot_be_created_for_foreign_company(base_url, make_officer):
    officer_a = make_officer("a")
    officer_b = make_officer("b")
    r = request("POST", base_url + "/api/alerts", json={
        "companyId": officer_b["companyId"],
        "changeEventId": 1,
        "relevance": "LOW",
        "summary": "cross-company attempt",
    }, headers=bearer(officer_a["token"]))
    assert r.status_code == 403


def test_company_list_scoped_to_own_company(base_url, make_officer):
    officer = make_officer()
    r = request("GET", base_url + "/api/companies", headers=bearer(officer["token"]))
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert ids == {officer["companyId"]}


def test_company_foreign_access_forbidden(base_url, make_officer):
    officer_a = make_officer("a")
    officer_b = make_officer("b")
    r = request("GET", base_url + f"/api/companies/{officer_b['companyId']}",
                headers=bearer(officer_a["token"]))
    assert r.status_code == 403
