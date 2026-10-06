"""CLI entry point: ``python -m docproc.main --input <url|path> ...``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .exceptions import DocprocError
from .process import process


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the docproc CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m docproc.main",
        description="Fetch, extract and clean a gazette/document version.",
    )
    parser.add_argument(
        "--input", required=True, help="Document URL or local filesystem path"
    )
    parser.add_argument(
        "--regulation-id", required=True, type=int, help="Target regulation id"
    )
    parser.add_argument(
        "--version", required=True, type=int, dest="version_no", help="Target version number"
    )
    parser.add_argument("--source", default="RBI", help="Source code (default: RBI)")
    parser.add_argument(
        "--storage-root",
        default=None,
        help="Override storage root (default: STORAGE_ROOT env or project storage/)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Returns:
        0 on success, 1 on a handled pipeline error (details on stderr).
    """
    args = build_parser().parse_args(argv)
    try:
        manifest = process(
            args.input,
            args.regulation_id,
            args.version_no,
            args.source,
            storage_root=args.storage_root,
        )
    except DocprocError as exc:
        print(f"docproc: error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
