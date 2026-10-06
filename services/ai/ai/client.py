"""Thin HTTP client for the live Spring Boot backend (read + alert emission)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)


class BackendError(RuntimeError):
    pass


class BackendClient:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 timeout: float = 15.0):
        self.base_url = (base_url or config.api_base()).rstrip("/")
        self.timeout = timeout
        self._token = token
        self._session = requests.Session()

    # -- auth ------------------------------------------------------------
    @property
    def token(self) -> str | None:
        return self._token

    def login(self, email: str | None = None, password: str | None = None) -> str:
        payload = {
            "email": email or config.admin_email(),
            "password": password or config.admin_password(),
        }
        data = self._request("POST", "/api/auth/login", json=payload, auth=False)
        token = data.get("token")
        if not token:
            raise BackendError(f"login response missing token: {data!r}")
        self._token = token
        return token

    def ensure_token(self) -> str:
        if not self._token:
            self.login()
        return self._token or ""

    # -- reads -----------------------------------------------------------
    def get_companies(self) -> list[dict]:
        return self._request("GET", "/api/companies")

    def get_company(self, company_id: int) -> dict:
        return self._request("GET", f"/api/companies/{company_id}")

    def get_profile(self, company_id: int) -> dict:
        return self._request("GET", f"/api/companies/{company_id}/profile")

    def get_events(self) -> list[dict]:
        return self._request("GET", "/api/events")

    def get_regulation(self, regulation_id: int) -> dict:
        return self._request("GET", f"/api/regulations/{regulation_id}")

    def get_versions(self, regulation_id: int) -> list[dict]:
        return self._request("GET", f"/api/regulations/{regulation_id}/versions")

    def get_version(self, regulation_id: int, version_id: int) -> dict:
        return self._request(
            "GET", f"/api/regulations/{regulation_id}/versions/{version_id}")

    # -- writes ----------------------------------------------------------
    def create_alert(self, payload: dict) -> dict:
        return self._request("POST", "/api/alerts", json=payload)

    # -- internals -------------------------------------------------------
    def _request(self, method: str, path: str, *, json: dict | None = None,
                 auth: bool = True, _retried: bool = False) -> Any:
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}
        if auth:
            headers["Authorization"] = f"Bearer {self.ensure_token()}"
        try:
            resp = self._session.request(
                method, url, json=json, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise BackendError(f"{method} {url} failed: {exc}") from exc

        if resp.status_code in (401, 403) and auth and not _retried:
            # token may have expired mid-run -> re-login once
            self.login()
            return self._request(method, path, json=json, auth=True, _retried=True)

        if resp.status_code >= 400:
            body = resp.text[:500]
            raise BackendError(f"{method} {url} -> HTTP {resp.status_code}: {body}")
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise BackendError(f"{method} {url} returned non-JSON body") from exc

    def close(self) -> None:
        self._session.close()


def strip_html(content: str) -> str:
    """Best-effort HTML -> plain text for backend-stored version content."""
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", content or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()
