"""docproc — gazette/document retrieval, extraction and cleaning service.

Pipeline: fetch -> extract -> clean -> process (manifest writer).
"""

from __future__ import annotations

__version__ = "1.0"

from .process import process

__all__ = ["process", "__version__"]
