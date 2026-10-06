"""CLI entrypoint: python -m ai.main --regulation-id N --version N [--event-id E]

Prints the §2.4 analysis JSON on stdout; emission/indexing reports go to stderr
unless --quiet is passed. Exit code 0 on success, 2 on analysis failure.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .analyze import AnalysisError, run_analysis


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ai.main",
        description="Run the regulatory change analysis pipeline (PLAN.md §2.4).")
    parser.add_argument("--regulation-id", type=int, required=True,
                        help="regulation id in the backend")
    parser.add_argument("--version", type=int, required=True, dest="version",
                        help="new version number to analyze")
    parser.add_argument("--event-id", type=int, default=None,
                        help="change event id (default: newest event for the regulation)")
    parser.add_argument("--no-emit", action="store_true",
                        help="skip POST /api/alerts emission")
    parser.add_argument("--offline", action="store_true",
                        help="no backend calls (no regulation meta, profiles, events)")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress stderr reports")
    parser.add_argument("--verbose", action="store_true",
                        help="debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr)

    try:
        result = run_analysis(
            regulation_id=args.regulation_id,
            version_no=args.version,
            event_id=args.event_id,
            emit=not args.no_emit,
            offline=args.offline,
        )
    except AnalysisError as exc:
        print(f"analysis failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI must fail loudly but cleanly
        print(f"analysis failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.analysis, indent=2, ensure_ascii=False))
    if not args.quiet:
        print(json.dumps({"emission": result.emission,
                          "indexing": result.indexing},
                         ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
