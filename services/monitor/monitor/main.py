"""CLI entry point for the monitor service.

Usage::

    python -m monitor.main --once [--dry-run] [--source RBI]
    python -m monitor.main --interval 3600 [--dry-run]

``--dry-run`` performs detection and prints the signed webhook headers
without sending anything to the backend.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from .config import Settings, SourceConfig, load_settings, load_sources
from .runner import MonitorRunner, RunSummary

log = logging.getLogger("monitor")


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m monitor.main",
        description="Watch regulation sources, detect changes, notify the backend webhook.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="run a single check cycle (default)")
    mode.add_argument("--interval", type=float, metavar="SECONDS",
                      help="poll continuously with SECONDS between cycles")
    parser.add_argument("--dry-run", action="store_true",
                        help="detect and print signed headers without sending")
    parser.add_argument("--source", action="append", metavar="CODE",
                        help="restrict the cycle to one source code (repeatable)")
    parser.add_argument("--config", metavar="PATH",
                        help="override path to sources.yaml")
    parser.add_argument("--log-level", default=os.environ.get("MONITOR_LOG_LEVEL", "INFO"),
                        metavar="LEVEL", help="logging level (default INFO)")
    return parser


def _emit(summary: RunSummary, dry_run: bool, out=None) -> None:
    """Print the JSON summary plus signed headers in dry-run mode."""
    out = out or sys.stdout
    out.write(json.dumps(summary.to_dict(), indent=2, ensure_ascii=True) + "\n")
    if dry_run:
        for outcome in summary.outcomes:
            if not outcome.changed:
                continue
            out.write(f"[dry-run] {outcome.code} {outcome.url}\n")
            for name, value in outcome.headers.items():
                out.write(f"  {name}: {value}\n")
    out.flush()


def run_single(settings: Settings, sources: list[SourceConfig], args: argparse.Namespace) -> RunSummary:
    """Execute one cycle and print its summary."""
    only = {code.upper() for code in args.source} if args.source else None
    runner = MonitorRunner(settings, sources)
    summary = runner.run_once(dry_run=args.dry_run, only=only)
    _emit(summary, args.dry_run)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 on success, 2 on configuration errors,
        1 on interrupted polling.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = load_settings()
        if args.config:
            settings = replace(settings, sources_path=Path(args.config))
        sources = load_sources(settings.sources_path)
    except (OSError, ValueError) as exc:
        log.error("configuration error: %s", exc)
        return 2

    if args.interval is None:
        run_single(settings, sources, args)
        return 0

    if args.interval <= 0:
        parser.error("--interval must be greater than 0")
    log.info("polling every %.0fs (dry_run=%s)", args.interval, args.dry_run)
    try:
        while True:
            run_single(settings, sources, args)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("stopped by user")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
