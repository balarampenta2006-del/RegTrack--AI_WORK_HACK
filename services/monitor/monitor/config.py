"""Runtime configuration for the monitor service.

Environment variables (shared contract, PLAN.md §2.1):

===============  ==========================================================
API_BASE         backend base URL, default ``http://localhost:8080``
WEBHOOK_SECRET   shared HMAC secret,
                 default ``dev-webhook-shared-secret-please-change``
MONITOR_STORAGE_DIR      snapshot root, default ``<repo>/storage/snapshots``
MONITOR_SOURCES_FILE     override path to ``sources.yaml``
MONITOR_NOTIFY_INITIAL   ``true``/``false`` (default ``true``): send a
                         webhook for the very first snapshot of a source
MONITOR_PAYLOAD_MODE     ``text`` (default) or ``html`` — what goes into
                         the webhook ``content`` field
MONITOR_TIMEOUT          fetch timeout in seconds (default 30)
FIRECRAWL_API_KEY        enables the optional ``firecrawl`` engine
FIRECRAWL_API_URL        default ``https://api.firecrawl.dev``
===============  ==========================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_API_BASE = "http://localhost:8080"
DEFAULT_WEBHOOK_SECRET = "dev-webhook-shared-secret-please-change"
DEFAULT_TIMEOUT_SECONDS = 30.0
# Plain Mozilla token: mca.gov.in serves 403 to full Chrome strings and this
# works for MCA/SEBI; override per source via `user_agent` in sources.yaml.
DEFAULT_USER_AGENT = "Mozilla/5.0"
SUPPORTED_ENGINES = ("http", "playwright", "firecrawl", "file")


@dataclass(frozen=True)
class SourceConfig:
    """One watched regulation source (mirrors a seeded ``regulation_sources`` row)."""

    code: str
    name: str
    base_url: str
    watch_url: str
    engine: str = "http"
    enabled: bool = True
    user_agent: str | None = None


@dataclass(frozen=True)
class Settings:
    """Runtime settings resolved from environment variables and defaults."""

    api_base: str
    webhook_secret: str
    storage_dir: Path
    sources_path: Path
    notify_initial: bool
    payload_mode: str
    timeout: float
    user_agent: str

    @property
    def webhook_url(self) -> str:
        """Full URL of the backend change-detection webhook (PLAN.md §1.2)."""
        return f"{self.api_base.rstrip('/')}/api/webhooks/changedetection"


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable (1/true/yes/on)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def find_repo_root() -> Path:
    """Walk upwards from this file until a repository marker is found.

    Returns:
        The project root (contains ``.agents`` or ``docker-compose.yml``),
        or the current working directory when no marker exists.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / ".agents").is_dir() or (parent / "docker-compose.yml").is_file():
            return parent
    return Path.cwd()


def load_settings() -> Settings:
    """Build :class:`Settings` from environment variables (PLAN.md §2.1)."""
    root = find_repo_root()
    storage = os.environ.get("MONITOR_STORAGE_DIR") or str(root / "storage" / "snapshots")
    sources = os.environ.get("MONITOR_SOURCES_FILE") or str(Path(__file__).with_name("sources.yaml"))
    payload_mode = (os.environ.get("MONITOR_PAYLOAD_MODE") or "text").strip().lower()
    if payload_mode not in {"text", "html"}:
        payload_mode = "text"
    return Settings(
        api_base=(os.environ.get("API_BASE") or DEFAULT_API_BASE).rstrip("/"),
        webhook_secret=os.environ.get("WEBHOOK_SECRET") or DEFAULT_WEBHOOK_SECRET,
        storage_dir=Path(storage),
        sources_path=Path(sources),
        notify_initial=_env_bool("MONITOR_NOTIFY_INITIAL", True),
        payload_mode=payload_mode,
        timeout=float(os.environ.get("MONITOR_TIMEOUT") or DEFAULT_TIMEOUT_SECONDS),
        user_agent=os.environ.get("MONITOR_USER_AGENT") or DEFAULT_USER_AGENT,
    )


def load_sources(path: Path) -> list[SourceConfig]:
    """Parse ``sources.yaml`` into :class:`SourceConfig` objects.

    Args:
        path: YAML file with a top-level ``sources`` list.

    Returns:
        Enabled and disabled sources in file order.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file contains no usable source entries.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("sources") or []
    if not isinstance(entries, list):
        raise ValueError(f"'sources' must be a list in {path}")

    configs: list[SourceConfig] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "").strip().upper()
        watch_url = str(entry.get("watch_url") or entry.get("url") or "").strip()
        if not code or not watch_url:
            continue
        engine = str(entry.get("engine") or "http").strip().lower()
        if engine not in SUPPORTED_ENGINES:
            engine = "http"
        configs.append(
            SourceConfig(
                code=code,
                name=str(entry.get("name") or code).strip(),
                base_url=str(entry.get("base_url") or "").strip(),
                watch_url=watch_url,
                engine=engine,
                enabled=bool(entry.get("enabled", True)),
                user_agent=(str(entry["user_agent"]).strip() or None)
                if entry.get("user_agent")
                else None,
            )
        )
    if not configs:
        raise ValueError(f"no usable sources configured in {path}")
    return configs
