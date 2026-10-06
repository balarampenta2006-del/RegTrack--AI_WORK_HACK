"""CLI tests: ``python -m docproc.main``."""

from __future__ import annotations

import json
from pathlib import Path

from docproc.main import main


def test_cli_success(
    sample_pdf: Path, storage_root: Path, capsys
) -> None:
    code = main(
        [
            "--input", str(sample_pdf),
            "--regulation-id", "3",
            "--version", "1",
            "--source", "RBI",
            "--storage-root", str(storage_root),
        ]
    )
    assert code == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["regulation_id"] == 3
    assert manifest["version_no"] == 1
    assert manifest["method"] == "pdf"
    assert manifest["content_path"] == "storage/processed/3/v1.txt"


def test_cli_missing_input_exits_nonzero(
    tmp_path: Path, storage_root: Path, capsys
) -> None:
    code = main(
        [
            "--input", str(tmp_path / "absent.pdf"),
            "--regulation-id", "3",
            "--version", "1",
            "--storage-root", str(storage_root),
        ]
    )
    assert code == 1
    assert "error" in capsys.readouterr().err.lower()
