"""Alert emission: POST /api/alerts for every non-NONE relevance entry (§2.4)."""

from __future__ import annotations

import logging
from typing import Any

from . import config
from .client import BackendClient, BackendError
from .relevance import fetch_company_profiles

log = logging.getLogger(__name__)


def resolve_event_id(client: BackendClient, regulation_id: int,
                     event_id: int | None = None) -> tuple[int | None, str]:
    """Use the caller-provided event id, else newest GET /api/events match."""
    if event_id is not None:
        return int(event_id), "provided"
    try:
        events = client.get_events() or []
    except BackendError as exc:
        return None, f"events lookup failed: {exc}"
    matches = [e for e in events if e.get("regulationId") == regulation_id]
    if not matches:
        return None, f"no change event for regulation {regulation_id}"
    matches.sort(key=lambda e: e.get("id") or 0, reverse=True)
    return int(matches[0]["id"]), "matched from /api/events"


def _alert_payload(analysis: dict, entry: dict, event_id: int,
                   email: str | None) -> dict:
    key_changes = analysis.get("key_changes") or []
    affected = analysis.get("affected_entities") or []
    required = analysis.get("required_actions") or []
    affected_areas = ", ".join((key_changes + affected)[:4])[:1000]
    required_action = " ".join(required)[:1000] or analysis.get("summary", "")[:1000]
    return {
        "companyId": int(entry["company_id"]),
        "changeEventId": int(event_id),
        "relevance": entry["level"],
        "summary": (analysis.get("summary") or "")[:1000],
        "affectedAreas": affected_areas,
        "effectiveDate": analysis.get("effective_date"),
        "requiredAction": required_action,
        "emailRecipients": email or None,
    }


def emit_alerts(analysis: dict, event_id: int | None = None,
                client: BackendClient | None = None,
                company_emails: dict[int, str] | None = None) -> dict[str, Any]:
    """Create one alert per relevance entry with level != NONE.

    Returns an emission report:
      {"status": "verified"|"deferred"|"skipped",
       "event_id": int|null, "emitted": [alertId...], "deferred": [reason...]}
    Never raises for backend failures - failures are reported as deferred.
    """
    report: dict[str, Any] = {
        "status": "skipped",
        "event_id": None,
        "emitted": [],
        "deferred": [],
        "reason": "",
    }

    relevance = analysis.get("relevance") or []
    actionable = [r for r in relevance if r.get("level") != "NONE"]
    if not actionable:
        report["reason"] = "no relevance entries above NONE"
        return report

    regulation_id = int(analysis.get("regulation_id") or 0)
    own_client = client is None
    client = client or BackendClient()
    try:
        resolved_event, event_note = resolve_event_id(client, regulation_id, event_id)
        report["event_id"] = resolved_event
        if resolved_event is None:
            report["status"] = "deferred"
            report["reason"] = event_note
            return report

        emails = dict(company_emails or {})
        if not emails:
            try:
                for entry in fetch_company_profiles(client):
                    company = entry.get("company") or {}
                    profile = entry.get("profile") or {}
                    company_id = company.get("id")
                    if company_id is not None:
                        emails[int(company_id)] = (
                            profile.get("complianceContactEmail") or "")
            except Exception as exc:  # noqa: BLE001 - emails are optional
                log.warning("could not resolve compliance emails: %s", exc)

        for entry in actionable:
            payload = _alert_payload(analysis, entry, resolved_event,
                                     emails.get(int(entry["company_id"])))
            try:
                created = client.create_alert(payload)
                report["emitted"].append(
                    created.get("id") if isinstance(created, dict) else None)
            except BackendError as exc:
                report["deferred"].append(
                    f"company {entry['company_id']}: {exc}")
                log.warning("alert emission failed: %s", exc)

        if report["emitted"]:
            report["status"] = "verified"
            report["reason"] = (f"{len(report['emitted'])} alert(s) created "
                                f"for event {resolved_event}")
        else:
            report["status"] = "deferred"
            report["reason"] = report["deferred"][0] if report["deferred"] else "unknown"
        return report
    finally:
        if own_client:
            client.close()


def default_api_base() -> str:
    return config.api_base()
