"""Relevance scoring unit tests with fake profiles (no network)."""

from ai.relevance import (RelevanceContext, build_context, extract_signals,
                          score_all, score_profile)

CTX = RelevanceContext(
    source_code="RBI",
    regulation_title="Master Direction - Digital Lending (Amended)",
    keywords=["digital", "lending", "kyc", "video", "borrower", "consent"],
    text=("Regulated Entities and NBFCs shall undertake customer due diligence "
          "and verify the borrower using video KYC before digital lending."),
)


def test_high_relevance_for_matching_profile():
    profile = {"industry_sectors": "Banking, NBFC, Fintech",
               "regulatory_bodies": "RBI", "jurisdictions": "India"}
    company = {"id": 1, "name": "Acme Fintech Ltd"}
    entry = score_profile(profile, company, CTX)
    assert entry["level"] == "HIGH"
    assert entry["company_id"] == 1
    assert entry["company_name"] == "Acme Fintech Ltd"
    assert entry["rationale"]
    assert set(entry) == {"company_id", "company_name", "level", "rationale"}


def test_none_relevance_for_unrelated_profile():
    profile = {"industry_sectors": "Textiles, Manufacturing",
               "regulatory_bodies": "Ministry of Textiles",
               "jurisdictions": "India"}
    company = {"id": 2, "name": "Textiles Inc"}
    entry = score_profile(profile, company, CTX)
    assert entry["level"] == "NONE"


def test_falls_back_to_company_industry_when_profile_empty():
    company = {"id": 5, "name": "Payments Co", "industry": "Fintech & Payments"}
    entry = score_profile({}, company, CTX)
    assert entry["level"] in {"HIGH", "MEDIUM"}
    assert "sector match" in entry["rationale"]


def test_body_inferred_from_sector_when_bodies_empty():
    signals = extract_signals({"industry_sectors": "Banking, Capital Market"},
                              {"id": 1, "name": "x"})
    assert "RBI" in signals["bodies"]
    assert "SEBI" in signals["bodies"]


def test_score_all_is_sorted_and_contract_shaped():
    profiles = [
        {"company": {"id": 2, "name": "Textiles Inc"},
         "profile": {"industry_sectors": "Textiles"}},
        {"company": {"id": 1, "name": "Acme Fintech Ltd"},
         "profile": {"industry_sectors": "Banking, NBFC",
                     "regulatory_bodies": "RBI"}},
    ]
    entries = score_all(profiles, CTX)
    assert [e["company_id"] for e in entries] == [1, 2]
    assert entries[0]["level"] == "HIGH"
    assert entries[1]["level"] == "NONE"
    for entry in entries:
        assert entry["level"] in {"HIGH", "MEDIUM", "LOW", "NONE"}
        assert isinstance(entry["rationale"], str) and entry["rationale"]


def test_jurisdiction_mismatch_lowers_score():
    profile = {"industry_sectors": "Banking", "regulatory_bodies": "RBI",
               "jurisdictions": "European Union"}
    entry = score_profile(profile, {"id": 3, "name": "EU Bank"}, CTX)
    assert entry["level"] in {"MEDIUM", "LOW", "NONE"}
    assert "no jurisdiction overlap" in entry["rationale"]


def test_build_context_extracts_keywords():
    ctx = build_context(
        source_code="RBI",
        regulation_title="Digital Lending",
        analysis_fields={
            "summary": "Updated video KYC norms for lenders.",
            "key_changes": ["Mandatory video KYC verification"],
            "required_actions": ["Update KYC policy"],
            "affected_entities": ["NBFCs"],
        },
        text="REs shall complete video KYC.",
    )
    assert ctx.source_code == "RBI"
    assert "kyc" in ctx.keywords
    assert ctx.text
