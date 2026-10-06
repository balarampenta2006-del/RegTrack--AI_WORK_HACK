"""Company relevance scoring: profiles from the live backend vs regulation text.

Scoring combines three signals per profile (PLAN.md mandate):
  * regulatory_bodies vs the regulation source code (RBI/SEBI/MCA ...)
  * industry_sectors vs regulation keywords / text
  * jurisdictions vs the regulation's jurisdiction hint
plus a token-overlap bonus. Output uses the §2.4 contract entry shape:
  {"company_id", "company_name", "level": HIGH|MEDIUM|LOW|NONE, "rationale"}
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .client import BackendClient, BackendError

log = logging.getLogger(__name__)

VALID_LEVELS = ("HIGH", "MEDIUM", "LOW", "NONE")

HIGH_THRESHOLD = 0.62
MEDIUM_THRESHOLD = 0.38
LOW_THRESHOLD = 0.18

# source code -> industries it typically regulates (used when profile bodies empty)
_SOURCE_INDUSTRY_HINTS = {
    "RBI": {"banking", "bank", "nbfc", "fintech", "payment", "microfinance",
            "lending", "credit", "financial"},
    "SEBI": {"securities", "capital market", "stock", "mutual fund", "listed",
             "issuer", "intermediary", "depository", "asset management"},
    "MCA": {"company", "corporate", "incorporation", "director", "listed"},
    "IRDAI": {"insurance"},
    "PFRDA": {"pension"},
    "MeITY": {"data protection", "digital", "it"},
    "RBI/SEBI": set(),
}

# sector keyword -> likely regulator bodies (fallback when bodies empty)
_SECTOR_BODIES = {
    "bank": ["RBI"], "banking": ["RBI"], "nbfc": ["RBI"], "fintech": ["RBI"],
    "payment": ["RBI"], "microfinance": ["RBI"], "lending": ["RBI"],
    "credit": ["RBI"], "financial": ["RBI"],
    "securities": ["SEBI"], "capital market": ["SEBI"], "stock": ["SEBI"],
    "mutual fund": ["SEBI"], "listed": ["SEBI"], "depository": ["SEBI"],
    "issuer": ["SEBI"],
    "company": ["MCA"], "corporate": ["MCA"], "incorporation": ["MCA"],
    "insurance": ["IRDAI"], "pension": ["PFRDA"],
}

_GENERIC_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "services", "service", "sector", "industry", "others", "other", "any",
    "ltd", "limited", "pvt", "private", "group", "house",
}


@dataclass
class RelevanceContext:
    source_code: str = ""
    regulation_title: str = ""
    keywords: list[str] = field(default_factory=list)
    text: str = ""
    jurisdiction_hint: str = "India"

    @property
    def haystack(self) -> str:
        return " ".join([
            self.source_code, self.regulation_title, " ".join(self.keywords),
            self.text[:12000],
        ]).lower()


# ---------------------------------------------------------------------------
# profile signal extraction
# ---------------------------------------------------------------------------
def _split_terms(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(v).strip() for v in raw if str(v).strip()]
    parts = re.split(r"[,;/|\n]+", str(raw))
    return [p.strip() for p in parts if p.strip()]


def extract_signals(profile: dict | None, company: dict | None) -> dict:
    profile = profile or {}
    company = company or {}

    sectors = _split_terms(
        profile.get("industry_sectors") or profile.get("industrySectors")
        or profile.get("sectors") or company.get("industry") or "")
    bodies = _split_terms(
        profile.get("regulatory_bodies") or profile.get("regulatoryBodies")
        or profile.get("regulators") or "")
    jurisdictions = _split_terms(
        profile.get("jurisdictions") or profile.get("jurisdiction") or "")

    # infer regulator bodies from sectors when profile does not declare them
    if not bodies:
        inferred: list[str] = []
        for sector in sectors:
            lowered = sector.lower()
            for token, regulator_list in _SECTOR_BODIES.items():
                if token in lowered:
                    for regulator in regulator_list:
                        if regulator not in inferred:
                            inferred.append(regulator)
        bodies = inferred

    return {
        "sectors": sectors,
        "bodies": bodies,
        "jurisdictions": jurisdictions,
        "email": (profile.get("complianceContactEmail")
                  or profile.get("compliance_contact_email") or ""),
        "raw_profile": profile,
    }


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) >= 3 and w not in _GENERIC_WORDS}


def _sector_hits(sectors: list[str], ctx: RelevanceContext) -> list[str]:
    haystack = ctx.haystack
    haystack_words = _words(ctx.text) | _words(" ".join(ctx.keywords))
    hits: list[str] = []
    for sector in sectors:
        sector_lower = sector.lower()
        sector_words = _words(sector)
        matched_keyword = next(
            (kw for kw in ctx.keywords
             if len(kw) >= 4 and kw.lower() in sector_lower), None)
        matched_word = next(
            (w for w in sector_words if len(w) >= 4 and re.search(
                rf"\b{re.escape(w)}", haystack)), None)
        source_hint = any(
            hint in sector_lower
            for hint in _SOURCE_INDUSTRY_HINTS.get(ctx.source_code.upper(), set()))
        if matched_keyword or matched_word or source_hint:
            hits.append(sector)
        elif sector_words & haystack_words and len(sector_words & haystack_words) >= 2:
            hits.append(sector)
    return hits


def _body_hits(bodies: list[str], ctx: RelevanceContext) -> list[str]:
    haystack = ctx.haystack
    source = (ctx.source_code or "").upper()
    hits: list[str] = []
    for body in bodies:
        body_upper = body.upper()
        if source and (body_upper == source or source in body_upper
                       or body_upper in source.split("/")):
            hits.append(body)
            continue
        if len(body) >= 3 and re.search(rf"\b{re.escape(body.lower())}", haystack):
            hits.append(body)
    return hits


def _jurisdiction_hits(jurisdictions: list[str], ctx: RelevanceContext) -> tuple[list[str], bool]:
    """Returns (matched, unknown) - unknown means profile declares none."""
    if not jurisdictions:
        return [], True
    haystack = ctx.haystack
    hint = (ctx.jurisdiction_hint or "").lower()
    hits = []
    for jurisdiction in jurisdictions:
        lowered = jurisdiction.lower()
        if lowered and (lowered in haystack or (hint and hint in lowered)
                        or (lowered in {"india", "in"} and hint == "india")):
            hits.append(jurisdiction)
    return hits, False


def _overlap_ratio(signals: dict, ctx: RelevanceContext) -> float:
    # jurisdictions are scored separately - exclude them to avoid double counting
    profile_words = _words(" ".join(signals["sectors"] + signals["bodies"]))
    if not profile_words:
        return 0.0
    ctx_words = _words(ctx.haystack)
    if not ctx_words:
        return 0.0
    inter = profile_words & ctx_words
    return len(inter) / max(1, min(len(profile_words), len(ctx_words)))


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def score_profile(profile: dict | None, company: dict | None,
                  ctx: RelevanceContext) -> dict:
    """Score ONE company against a regulation context (pure, no I/O)."""
    company = company or {}
    company_id = company.get("id") or (profile or {}).get("company_id") or 0
    company_name = (company.get("name")
                    or (profile or {}).get("company_name")
                    or f"company-{company_id}")

    signals = extract_signals(profile, company)
    has_signals = bool(signals["sectors"] or signals["bodies"]
                       or signals["jurisdictions"])

    body_matches = _body_hits(signals["bodies"], ctx)
    sector_matches = _sector_hits(signals["sectors"], ctx)
    juris_matches, juris_unknown = _jurisdiction_hits(signals["jurisdictions"], ctx)
    overlap = _overlap_ratio(signals, ctx)

    body_score = 1.0 if body_matches else 0.0
    sector_score = min(1.0, 0.75 + 0.25 * (len(sector_matches) - 1)) if sector_matches else 0.0
    if juris_unknown:
        juris_score = 0.5  # neutral: profile does not declare jurisdictions
    else:
        juris_score = 1.0 if juris_matches else 0.0

    score = (0.35 * body_score + 0.40 * sector_score
             + 0.15 * juris_score + 0.10 * min(1.0, overlap * 2))
    if not has_signals:
        score = min(score, 0.15)
    if not juris_unknown and not juris_matches:
        score *= 0.6  # declared jurisdiction outside the regulation's jurisdiction

    if score >= HIGH_THRESHOLD:
        level = "HIGH"
    elif score >= MEDIUM_THRESHOLD:
        level = "MEDIUM"
    elif score >= LOW_THRESHOLD:
        level = "LOW"
    else:
        level = "NONE"

    evidence: list[str] = []
    if body_matches:
        evidence.append(
            f"regulatory body match {body_matches} vs source "
            f"{ctx.source_code or 'n/a'}")
    if sector_matches:
        evidence.append(f"sector match {sector_matches}")
    if juris_matches:
        evidence.append(f"jurisdiction match {juris_matches}")
    elif not juris_unknown:
        evidence.append("no jurisdiction overlap")
    if overlap > 0:
        evidence.append(f"keyword overlap {overlap:.0%}")
    if not evidence:
        evidence.append("no sector/regulator/jurisdiction overlap")

    rationale = (
        f"Score {score:.2f} -> {level}: " + "; ".join(evidence) + "."
    )
    return {
        "company_id": int(company_id),
        "company_name": str(company_name),
        "level": level,
        "rationale": rationale,
    }


def score_all(profiles: list[dict], ctx: RelevanceContext) -> list[dict]:
    """profiles: [{"company": {...}, "profile": {...}}] -> §2.4 relevance[]."""
    results = [
        score_profile(entry.get("profile"), entry.get("company"), ctx)
        for entry in profiles
    ]
    results.sort(key=lambda item: item["company_id"])
    return results


def build_context(source_code: str = "", regulation_title: str = "",
                  analysis_fields: dict | None = None,
                  text: str = "") -> RelevanceContext:
    analysis_fields = analysis_fields or {}
    keywords: list[str] = []
    for key in ("summary",):
        value = analysis_fields.get(key)
        if value:
            keywords.extend(re.findall(r"[A-Za-z][A-Za-z\-']{2,}", str(value)))
    for key in ("key_changes", "required_actions", "affected_entities"):
        for item in analysis_fields.get(key) or []:
            keywords.extend(re.findall(r"[A-Za-z][A-Za-z\-']{2,}", str(item)))

    lowered_text = text.lower()
    seen: set[str] = set()
    ordered: list[str] = []
    for word in keywords:
        word_lower = word.lower()
        if word_lower in seen or word_lower in _GENERIC_WORDS or len(word_lower) < 3:
            continue
        seen.add(word_lower)
        if lowered_text and word_lower not in lowered_text:
            continue  # only terms actually present in the regulation text
        ordered.append(word_lower)
        if len(ordered) >= 25:
            break
    if not ordered and lowered_text:
        # fall back to distinctive terms from the regulation text itself
        for word in re.findall(r"[a-z][a-z\-']{3,}", lowered_text):
            if word not in _GENERIC_WORDS and word not in seen:
                seen.add(word)
                ordered.append(word)
            if len(ordered) >= 25:
                break

    return RelevanceContext(
        source_code=source_code or "",
        regulation_title=regulation_title or "",
        keywords=ordered[:25],
        text=text or "",
    )


# ---------------------------------------------------------------------------
# live fetch
# ---------------------------------------------------------------------------
def fetch_company_profiles(client: BackendClient | None = None,
                           offline: bool = False) -> list[dict]:
    """GET /api/companies + /api/companies/{id}/profile from the live backend."""
    if offline:
        return []
    own_client = client is None
    client = client or BackendClient()
    try:
        companies = client.get_companies() or []
        entries: list[dict] = []
        for company in companies:
            company_id = company.get("id")
            if company_id is None:
                continue
            try:
                profile = client.get_profile(int(company_id)) or {}
            except BackendError as exc:
                log.warning("profile fetch failed for company %s: %s",
                            company_id, exc)
                profile = {}
            entries.append({"company": company, "profile": profile})
        return entries
    except BackendError as exc:
        log.warning("company fetch failed: %s", exc)
        return []
    finally:
        if own_client:
            client.close()
