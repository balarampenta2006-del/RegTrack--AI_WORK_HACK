"""FastAPI wrapper tests (PLAN.md §2.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docproc.api import app

REQUIRED_MANIFEST_KEYS = {
    "regulation_id",
    "version_no",
    "source",
    "source_url",
    "method",
    "content_path",
    "content_sha256",
    "char_count",
    "ocr_used",
    "extracted_at",
    "pipeline_version",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "docproc"
    assert isinstance(body["ocr_available"], bool)


def test_process_endpoint(
    client: TestClient, sample_pdf: Path, storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    response = client.post(
        "/process",
        json={
            "input": str(sample_pdf),
            "regulation_id": 5,
            "version_no": 1,
            "source": "RBI",
        },
    )
    assert response.status_code == 200
    manifest = response.json()
    assert REQUIRED_MANIFEST_KEYS <= set(manifest.keys())
    assert manifest["regulation_id"] == 5
    assert manifest["version_no"] == 1
    assert manifest["method"] == "pdf"
    assert manifest["ocr_used"] is False
    assert (storage_root / "processed" / "5" / "v1.txt").is_file()


def test_process_endpoint_validation_error(client: TestClient) -> None:
    response = client.post("/process", json={"input": "", "regulation_id": 1, "version_no": 1})
    assert response.status_code == 422


def test_process_endpoint_empty_content_returns_422(
    client: TestClient, empty_pdf: Path, storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    if shutil.which("tesseract") is not None:
        pytest.skip("tesseract installed; degraded path not applicable")
    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    response = client.post(
        "/process",
        json={"input": str(empty_pdf), "regulation_id": 6, "version_no": 1, "source": "RBI"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "EmptyContentError"
    assert "tesseract" in body["detail"].lower()
