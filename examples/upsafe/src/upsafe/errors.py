"""Typed domain errors for upsafe.

Kept deliberately small: each maps to a single HTTP status in ``routes.py``.
Raising these (instead of returning sentinels) keeps the request handlers linear.
"""

from __future__ import annotations


class UpsafeError(Exception):
    """Base class for all upsafe domain errors."""


class EmptyUpload(UpsafeError):
    """The request carried no file part, or a zero-byte one."""


class FileTooLarge(UpsafeError):
    """The upload exceeded the configured maximum size."""


class TypeNotAllowed(UpsafeError):
    """The declared extension or sniffed content is not on the allow-list."""


class PathEscape(UpsafeError):
    """A resolved path fell outside the quarantine root — an invariant violation (500).

    This must be unreachable in normal operation (names are server-generated); it exists
    as a hard, fail-closed belt-and-suspenders guard, never a warning.
    """
