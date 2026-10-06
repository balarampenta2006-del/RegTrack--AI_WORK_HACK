"""Configuration contract tests (PLAN.md §1 / §2.1)."""

from __future__ import annotations

from pathlib import Path

from monitor.config import load_settings, load_sources

PACKAGED_SOURCES = Path(__file__).resolve().parents[1] / "monitor" / "sources.yaml"


def test_packaged_sources_match_seeded_regulation_sources() -> None:
    """sources.yaml watches exactly the seeded codes and URLs."""
    sources = load_sources(PACKAGED_SOURCES)
    assert [source.code for source in sources] == ["MCA", "RBI", "SEBI"]
    assert all(source.enabled for source in sources)
    assert all(source.engine == "http" for source in sources)

    by_code = {source.code: source for source in sources}
    assert by_code["MCA"].watch_url == (
        "https://www.mca.gov.in/content/mca/global/en/acts-rules.html"
    )
    assert by_code["RBI"].watch_url == (
        "https://www.rbi.org.in/Scripts/BS_ViewMasNotifications.aspx"
    )
    assert by_code["SEBI"].watch_url == (
        "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=2&ssid=9&smid=11"
    )
    assert by_code["MCA"].base_url == "https://www.mca.gov.in"
    assert by_code["RBI"].base_url == "https://www.rbi.org.in"
    assert by_code["SEBI"].base_url == "https://www.sebi.gov.in"


def test_settings_defaults_match_plan_contract() -> None:
    """Env-var defaults follow PLAN.md §2.1 and the webhook URL follows §1.2."""
    settings = load_settings()
    assert settings.webhook_url == "http://localhost:8080/api/webhooks/changedetection"
    assert settings.webhook_secret == "dev-webhook-shared-secret-please-change"
    assert settings.payload_mode == "text"
    assert settings.notify_initial is True
    assert settings.storage_dir.name == "snapshots"


def test_sources_yaml_rejects_empty_config(tmp_path: Path) -> None:
    """An unusable config is a hard configuration error, not a silent no-op."""
    empty = tmp_path / "sources.yaml"
    empty.write_text("sources: []\n", encoding="utf-8")
    try:
        load_sources(empty)
    except ValueError as exc:
        assert "no usable sources" in str(exc)
    else:
        raise AssertionError("expected ValueError for empty sources.yaml")
