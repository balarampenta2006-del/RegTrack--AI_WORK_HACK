"""Pytest bootstrap: make the `ai` package importable from services/ai."""

import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))
