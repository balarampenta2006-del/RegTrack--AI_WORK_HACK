"""Government website monitoring service (Phase 2).

Fetches the seeded regulation source watch URLs (MCA, RBI, SEBI), detects
content changes via sha256 comparison plus unified diffs, stores snapshots
under ``storage/snapshots/<code>/`` and notifies the backend webhook with an
HMAC-SHA256 signed payload (PLAN.md §1.2).
"""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["__version__"]
