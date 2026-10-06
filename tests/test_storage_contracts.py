"""Storage contract validators (PLAN §2.3 manifest.json, §2.4 analysis JSON).

Pure functions + assertions: no network, no services required. When the
docproc/ai agents land real files under storage/, those files are validated
automatically (skipped until then).
"""

import glob
import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(r"D:\AI_Hack")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# --------------------------------------------------------------------------
# Schemas (PLAN §2.3 / §2.4)
# --------------------------------------------------------------------------

MANIFEST_REQUIRED = {
    "regulation_id": int,
    "version_no": int,
    "source": str,
    "source_url": str,
    "method": str,
    "content_path": str,
    "content_sha256": str,
    "char_count": int,
    "ocr_used": bool,
    "extracted_at": str,
    "pipeline_version": str,
}

ANALYSIS_REQUIRED = {
    "regulation_id": int,
    "version_no": int,
    "event_id": (int, type(None)),
    "analysis_mode": str,
    "model": str,
    "summary": str,
    "key_changes": list,
    "affected_entities": list,
    "effective_date": (str, type(None)),
    "required_actions": list,
    "risk_level": str,
    "relevance": list,
    "generated_at": str,
}

METHODS = {"html", "pdf", "ocr"}
RISK_LEVELS = {"HIGH", "MEDIUM", "LOW"}
RELEVANCE_LEVELS = {"HIGH", "MEDIUM", "LOW", "NONE"}
ANALYSIS_MODES = {"llm", "stub"}
RELEVANCE_REQUIRED = {"company_id", "company_name", "level", "rationale"}


def _type_ok(value, expected) -> bool:
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(expected, tuple):
        return any(_type_ok(value, e) for e in expected)
    return isinstance(value, expected)


def validate_manifest(obj) -> list[str]:
    """Return a list of contract violations (empty list == valid §2.3 manifest)."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["manifest must be a JSON object"]
    for key, expected in MANIFEST_REQUIRED.items():
        if key not in obj:
            errors.append(f"missing required key: {key}")
        elif not _type_ok(obj[key], expected):
            errors.append(f"{key}: expected {expected.__name__ if hasattr(expected, '__name__') else expected}, "
                          f"got {type(obj[key]).__name__}")
    if "method" in obj and obj["method"] not in METHODS:
        errors.append(f"method must be one of {sorted(METHODS)}: {obj['method']!r}")
    if "content_sha256" in obj and isinstance(obj["content_sha256"], str) \
            and not SHA256_RE.match(obj["content_sha256"]):
        errors.append("content_sha256 must be a lowercase 64-char hex digest")
    if "char_count" in obj and _type_ok(obj["char_count"], int) and obj["char_count"] < 0:
        errors.append("char_count must be >= 0")
    if "extracted_at" in obj and isinstance(obj["extracted_at"], str) \
            and not ISO_RE.match(obj["extracted_at"]):
        errors.append(f"extracted_at must be ISO-8601: {obj['extracted_at']!r}")
    if "version_no" in obj and _type_ok(obj["version_no"], int) and obj["version_no"] < 1:
        errors.append("version_no must be >= 1")
    return errors


def validate_analysis(obj) -> list[str]:
    """Return a list of contract violations (empty list == valid §2.4 analysis)."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["analysis must be a JSON object"]
    for key, expected in ANALYSIS_REQUIRED.items():
        if key not in obj:
            errors.append(f"missing required key: {key}")
        elif not _type_ok(obj[key], expected):
            errors.append(f"{key}: expected {expected}, got {type(obj[key]).__name__}")

    if "summary" in obj and (not isinstance(obj["summary"], str) or not obj["summary"].strip()):
        errors.append("summary must be a non-empty string")
    if "analysis_mode" in obj and obj["analysis_mode"] not in ANALYSIS_MODES:
        errors.append(f"analysis_mode must be one of {sorted(ANALYSIS_MODES)}: {obj['analysis_mode']!r}")
    if "risk_level" in obj and obj["risk_level"] not in RISK_LEVELS:
        errors.append(f"risk_level must be one of {sorted(RISK_LEVELS)}: {obj['risk_level']!r}")

    eff = obj.get("effective_date", "missing")
    if eff is not None and not (isinstance(eff, str) and DATE_RE.match(eff)):
        errors.append(f"effective_date must be null or YYYY-MM-DD: {eff!r}")

    for key in ("key_changes", "affected_entities", "required_actions"):
        if key in obj and isinstance(obj[key], list) \
                and not all(isinstance(i, str) for i in obj[key]):
            errors.append(f"{key} must be a list of strings")

    if "relevance" in obj:
        if not isinstance(obj["relevance"], list):
            errors.append("relevance must be a list")
        else:
            for idx, item in enumerate(obj["relevance"]):
                if not isinstance(item, dict):
                    errors.append(f"relevance[{idx}] must be an object")
                    continue
                missing = RELEVANCE_REQUIRED - set(item)
                if missing:
                    errors.append(f"relevance[{idx}] missing keys: {sorted(missing)}")
                    continue
                if item["level"] not in RELEVANCE_LEVELS:
                    errors.append(f"relevance[{idx}].level must be one of "
                                  f"{sorted(RELEVANCE_LEVELS)}: {item['level']!r}")
                if not isinstance(item["rationale"], str) or not item["rationale"].strip():
                    errors.append(f"relevance[{idx}].rationale must be non-empty")
                if not _type_ok(item["company_id"], int):
                    errors.append(f"relevance[{idx}].company_id must be an int")

    if "generated_at" in obj and isinstance(obj["generated_at"], str) \
            and not ISO_RE.match(obj["generated_at"]):
        errors.append(f"generated_at must be ISO-8601: {obj['generated_at']!r}")
    if "version_no" in obj and _type_ok(obj["version_no"], int) and obj["version_no"] < 1:
        errors.append("version_no must be >= 1")
    return errors


# --------------------------------------------------------------------------
# Validator self-tests (the validators must catch violations)
# --------------------------------------------------------------------------

VALID_MANIFEST = {
    "regulation_id": 1,
    "version_no": 2,
    "source": "RBI",
    "source_url": "https://www.rbi.org.in/notifications/2026/x.html",
    "method": "html",
    "content_path": "storage/processed/1/v2.txt",
    "content_sha256": "a" * 64,
    "char_count": 1234,
    "ocr_used": False,
    "extracted_at": "2026-10-03T12:00:00Z",
    "pipeline_version": "1.0",
}

VALID_ANALYSIS = {
    "regulation_id": 1,
    "version_no": 2,
    "event_id": 7,
    "analysis_mode": "stub",
    "model": "stub-rules",
    "summary": "RBI tightened digital lending disclosures.",
    "key_changes": ["New KYC timeline"],
    "affected_entities": ["NBFCs"],
    "effective_date": "2026-11-01",
    "required_actions": ["Update policy"],
    "risk_level": "HIGH",
    "relevance": [{"company_id": 1, "company_name": "Acme", "level": "HIGH",
                   "rationale": "Lending business"}],
    "generated_at": "2026-10-03T12:00:00Z",
}


def test_manifest_validator_accepts_contract_example():
    assert validate_manifest(dict(VALID_MANIFEST)) == []


def test_manifest_validator_rejects_missing_keys():
    broken = dict(VALID_MANIFEST)
    del broken["content_sha256"]
    del broken["ocr_used"]
    errors = validate_manifest(broken)
    assert any("content_sha256" in e for e in errors)
    assert any("ocr_used" in e for e in errors)


def test_manifest_validator_rejects_bad_values():
    broken = dict(VALID_MANIFEST, method="ocr-output", char_count=-1,
                  extracted_at="yesterday", content_sha256="nope")
    errors = validate_manifest(broken)
    assert len(errors) >= 4


def test_manifest_validator_rejects_wrong_types():
    broken = dict(VALID_MANIFEST, ocr_used="false", char_count="12")
    errors = validate_manifest(broken)
    assert len(errors) >= 2


def test_analysis_validator_accepts_contract_example():
    assert validate_analysis(dict(VALID_ANALYSIS)) == []


def test_analysis_validator_accepts_null_effective_date():
    obj = dict(VALID_ANALYSIS, effective_date=None)
    assert validate_analysis(obj) == []


def test_analysis_validator_rejects_missing_keys():
    broken = dict(VALID_ANALYSIS)
    for key in ("summary", "risk_level", "relevance", "effective_date"):
        del broken[key]
    errors = validate_analysis(broken)
    assert len(errors) >= 4


def test_analysis_validator_rejects_bad_enums():
    broken = dict(VALID_ANALYSIS, risk_level="CRITICAL", analysis_mode="magic",
                  relevance=[{"company_id": 1, "company_name": "Acme",
                              "level": "SURE", "rationale": "because"}])
    errors = validate_analysis(broken)
    assert any("risk_level" in e for e in errors)
    assert any("analysis_mode" in e for e in errors)
    assert any("level" in e for e in errors)


def test_analysis_validator_rejects_empty_summary_and_bad_date():
    broken = dict(VALID_ANALYSIS, summary="   ", effective_date="03/11/2026")
    errors = validate_analysis(broken)
    assert any("summary" in e for e in errors)
    assert any("effective_date" in e for e in errors)


# --------------------------------------------------------------------------
# Real artifacts (auto-enable when docproc/ai land output)
# --------------------------------------------------------------------------

def _real_files(pattern: str):
    return sorted(glob.glob(str(PROJECT_ROOT / pattern), recursive=True))


def test_real_manifests_satisfy_contract():
    files = _real_files("storage/processed/**/manifest.json")
    if not files:
        pytest.skip("no storage/processed/**/manifest.json yet (docproc agent pending)")
    problems = []
    for path in files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path}: unreadable ({exc})")
            continue
        for err in validate_manifest(data):
            problems.append(f"{path}: {err}")
    assert not problems, problems


def test_real_analyses_satisfy_contract():
    files = _real_files("storage/analysis/**/*.json")
    if not files:
        pytest.skip("no storage/analysis/**/*.json yet (ai agent pending)")
    problems = []
    for path in files:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path}: unreadable ({exc})")
            continue
        for err in validate_analysis(data):
            problems.append(f"{path}: {err}")
    assert not problems, problems
