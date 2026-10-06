"""Orchestration: fetch each source, detect changes, notify the backend.

``MonitorRunner.run_once`` performs one full check cycle and is shared by the
CLI (``python -m monitor.main``) and the FastAPI wrapper (``POST /run``).
Fetcher and notifier are injectable for deterministic tests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from . import notifier as notifier_module
from .config import Settings, SourceConfig
from .notifier import NotifyResult, build_payload
from .retriever import FetchResult, fetch, utc_now_iso
from .snapshots import SnapshotStore, sha256_text

log = logging.getLogger("monitor.runner")

Fetcher = Callable[[SourceConfig], FetchResult]
Notifier = Callable[..., NotifyResult]


@dataclass
class SourceOutcome:
    """Result of checking a single source."""

    code: str
    url: str
    changed: bool
    error: str | None = None
    notified: bool = False
    dry_run: bool = False
    signature: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    diff_path: str | None = None
    status_code: int | None = None


@dataclass
class RunSummary:
    """Aggregated result of one check cycle."""

    checked: int
    changed: list[str]
    errors: list[dict[str, str]]
    outcomes: list[SourceOutcome]
    dry_run: bool
    started_at: str

    def to_dict(self) -> dict:
        """JSON-friendly summary (CLI output)."""
        return {
            "checked": self.checked,
            "changed": list(self.changed),
            "errors": list(self.errors),
            "dry_run": self.dry_run,
            "started_at": self.started_at,
        }


class MonitorRunner:
    """Runs change-detection cycles over the configured sources."""

    def __init__(
        self,
        settings: Settings,
        sources: Iterable[SourceConfig],
        *,
        fetcher: Fetcher | None = None,
        notifier: Notifier | None = None,
        store: SnapshotStore | None = None,
    ) -> None:
        """Args:
            settings: Runtime settings (storage dir, secret, payload mode...).
            sources: Watched sources from ``sources.yaml``.
            fetcher: Injectable retrieval function (defaults to ``retriever.fetch``).
            notifier: Injectable webhook sender (defaults to ``notifier.notify``).
            store: Injectable snapshot store (defaults to ``settings.storage_dir``).
        """
        self.settings = settings
        self.sources = list(sources)
        self.store = store or SnapshotStore(settings.storage_dir)
        self._fetcher = fetcher or self._default_fetcher
        self._notifier: Notifier = notifier or notifier_module.notify

    def _default_fetcher(self, source: SourceConfig) -> FetchResult:
        return fetch(
            source.watch_url,
            engine=source.engine,
            timeout=self.settings.timeout,
            user_agent=source.user_agent or self.settings.user_agent,
        )

    def run_once(self, *, dry_run: bool = False, only: set[str] | None = None) -> RunSummary:
        """Check every enabled source once.

        Args:
            dry_run: Detect and sign, but never POST to the backend.
            only: Optional set of source codes to restrict the cycle to.

        Returns:
            :class:`RunSummary` with per-source outcomes.
        """
        started_at = utc_now_iso()
        outcomes: list[SourceOutcome] = []
        for source in self.sources:
            if not source.enabled:
                continue
            if only is not None and source.code not in only:
                continue
            outcomes.append(self._check_one(source, dry_run))

        changed = [o.url for o in outcomes if o.changed]
        errors = [{"source": o.code, "url": o.url, "error": o.error or "unknown"}
                  for o in outcomes if o.error]
        summary = RunSummary(
            checked=len(outcomes),
            changed=changed,
            errors=errors,
            outcomes=outcomes,
            dry_run=dry_run,
            started_at=started_at,
        )
        log.info(
            "cycle complete: checked=%d changed=%d errors=%d dry_run=%s",
            summary.checked,
            len(changed),
            len(errors),
            dry_run,
        )
        return summary

    def _check_one(self, source: SourceConfig, dry_run: bool) -> SourceOutcome:
        try:
            fetched = self._fetcher(source)
        except Exception as exc:
            log.warning("fetch failed for %s (%s): %s", source.code, source.watch_url, exc)
            return SourceOutcome(code=source.code, url=source.watch_url, changed=False, error=str(exc))

        new_sha = sha256_text(fetched.text)
        previous = self.store.load_latest(source.code)
        initial = previous is None

        if not initial and sha256_text(previous.text) == new_sha:
            log.debug("%s unchanged (%s)", source.code, new_sha[:12])
            return SourceOutcome(
                code=source.code,
                url=fetched.url,
                changed=False,
                dry_run=dry_run,
                status_code=fetched.status_code,
            )

        diff_path = self.store.write_diff(
            source.code, previous.text if previous is not None else "", fetched.text
        )
        self.store.save(source.code, fetched, new_sha)

        if initial and not self.settings.notify_initial:
            log.info("%s initial snapshot stored (notification disabled)", source.code)
            return SourceOutcome(
                code=source.code,
                url=fetched.url,
                changed=False,
                dry_run=dry_run,
                diff_path=str(diff_path),
                status_code=fetched.status_code,
            )

        content = fetched.html if self.settings.payload_mode == "html" else fetched.text
        payload = build_payload(
            url=fetched.url,
            title=fetched.title or source.name,
            source_code=source.code,
            content=content,
            timestamp=fetched.fetched_at,
        )
        result = self._notifier(
            payload,
            endpoint=self.settings.webhook_url,
            secret=self.settings.webhook_secret,
            dry_run=dry_run,
            timeout=self.settings.timeout,
        )
        signature = result.headers.get(notifier_module.SIGNATURE_HEADER)
        reason = "initial snapshot" if initial else "content changed"
        log.info(
            "%s %s for %s (diff=%s, signature=%s, sent=%s)",
            source.code,
            reason,
            fetched.url,
            diff_path.name,
            signature,
            result.sent,
        )
        return SourceOutcome(
            code=source.code,
            url=fetched.url,
            changed=True,
            error=result.error,
            notified=result.sent,
            dry_run=dry_run,
            signature=signature,
            headers=dict(result.headers),
            diff_path=str(diff_path),
            status_code=result.status_code,
        )
