"""Exception hierarchy for the docproc pipeline."""

from __future__ import annotations


class DocprocError(Exception):
    """Base class for all expected docproc failures."""


class FetchError(DocprocError):
    """Raised when a document cannot be retrieved or copied into storage/raw."""


class ExtractionError(DocprocError):
    """Raised when a stored document cannot be opened or parsed."""


class UnsupportedFormatError(ExtractionError):
    """Raised when the document format is not recognised by any extraction path."""


class EmptyContentError(DocprocError):
    """Raised when extraction + cleaning produced no usable text."""
