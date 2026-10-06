"""Shared fixtures: isolated storage root, deterministic fixture texts, fake backend."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SERVICE_ROOT = Path(__file__).resolve().parent.parent
_TESTS_ROOT = Path(__file__).resolve().parent
for _path in (str(_SERVICE_ROOT), str(_TESTS_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from sample_data import NEW_TEXT, OLD_TEXT  # noqa: E402


class FakeClient:
    """In-memory stand-in for BackendClient (no network, records writes)."""

    def __init__(self, companies=None, profiles=None, events=None,
                 regulation=None, versions=None):
        self.companies = companies if companies is not None else [
            {"id": 1, "name": "Acme Fintech Ltd", "industry": "Banking & NBFC"},
            {"id": 2, "name": "Textiles Inc", "industry": "Textiles"},
        ]
        self.profiles = profiles if profiles is not None else {
            1: {"companyId": 1, "industry_sectors": "Banking, NBFC, Fintech",
                "regulatory_bodies": "RBI", "jurisdictions": "India",
                "complianceContactEmail": "cso@acme.test"},
            2: {"companyId": 2, "industry_sectors": "Textiles, Manufacturing",
                "regulatory_bodies": "Ministry of Textiles",
                "jurisdictions": "India",
                "complianceContactEmail": "ops@textiles.test"},
        }
        self.events = events if events is not None else [
            {"id": 7, "regulationId": 1, "sourceCode": "RBI"},
            {"id": 6, "regulationId": 2, "sourceCode": "RBI"},
        ]
        self.regulation = regulation if regulation is not None else {
            "id": 1, "title": "RBI Notification on Digital Lending (Amended)",
            "sourceCode": "RBI"}
        self.versions = versions or []
        self.created_alerts: list[dict] = []
        self.closed = False

    def get_companies(self):
        return self.companies

    def get_company(self, company_id: int):
        return next(c for c in self.companies if c["id"] == company_id)

    def get_profile(self, company_id: int):
        return self.profiles.get(company_id, {})

    def get_events(self):
        return self.events

    def get_regulation(self, regulation_id: int):
        return self.regulation

    def get_versions(self, regulation_id: int):
        return self.versions

    def get_version(self, regulation_id: int, version_id: int):
        raise AssertionError("no backend content fetch expected in tests")

    def create_alert(self, payload: dict) -> dict:
        self.created_alerts.append(payload)
        return {"id": 100 + len(self.created_alerts), **payload}

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own storage root and forced stub mode."""
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("AI_FORCE_STUB", "1")
    monkeypatch.setenv("API_BASE", "http://localhost:9")  # unreachable on purpose
    for var in ("OPENAI_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    from ai import config
    config.clear_provider_cache()
    yield tmp_path / "storage"
    config.clear_provider_cache()


@pytest.fixture()
def processed_storage(isolated_env):
    """storage/processed/1 with v1 (old) + v2 (new) fixture texts."""
    directory = isolated_env / "processed" / "1"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "v1.txt").write_text(OLD_TEXT, encoding="utf-8")
    (directory / "v2.txt").write_text(NEW_TEXT, encoding="utf-8")
    return directory


@pytest.fixture()
def processed_storage_new_only(isolated_env):
    """storage/processed/2 with only v2 - old version is missing."""
    directory = isolated_env / "processed" / "2"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "v2.txt").write_text(NEW_TEXT, encoding="utf-8")
    return directory


@pytest.fixture()
def fake_client():
    return FakeClient()
