"""Storage layout helpers shared by the docproc pipeline (PLAN.md §2.3)."""

from __future__ import annotations

import os
from pathlib import Path


def storage_root() -> Path:
    """Resolve the storage root directory.

    Honours the ``STORAGE_ROOT`` environment variable first, then walks up from
    this package looking for the project root (marked by ``.agents/`` or an
    existing ``storage/`` folder), and finally falls back to ``./storage``.

    Returns:
        Absolute path of the storage root directory.
    """
    env = os.environ.get("STORAGE_ROOT")
    if env:
        return Path(env).expanduser()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".agents").is_dir() or (parent / "storage").is_dir():
            return parent / "storage"
    return Path.cwd() / "storage"


def raw_dir(root: Path) -> Path:
    """Return ``<root>/raw`` (downloaded originals)."""
    return root / "raw"


def processed_dir(root: Path, regulation_id: int) -> Path:
    """Return ``<root>/processed/<regulation_id>``."""
    return root / "processed" / str(regulation_id)


def content_file(root: Path, regulation_id: int, version_no: int) -> Path:
    """Return the processed text file ``<root>/processed/<id>/v<n>.txt``."""
    return processed_dir(root, regulation_id) / f"v{version_no}.txt"


def content_path_str(root: Path, regulation_id: int, version_no: int) -> Path | str:
    """Manifest ``content_path``: posix path relative to the storage parent.

    In the default layout this equals ``storage/processed/<id>/v<n>.txt``
    exactly as specified in PLAN.md §2.3/§2.4.
    """
    target = content_file(root, regulation_id, version_no)
    try:
        return target.relative_to(root.parent).as_posix()
    except ValueError:
        return f"{root.name}/processed/{regulation_id}/v{version_no}.txt"
