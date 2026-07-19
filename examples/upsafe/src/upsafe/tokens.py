"""CSPRNG identifiers.

Two independent random values per upload, deliberately never equal:

- ``new_token``       — the download capability. 256 bits, URL-safe. Only ever a
  database key; it must never appear on the filesystem.
- ``new_stored_name`` — the on-disk filename. 128 bits, hex. Server-generated so no
  client string is ever a path component (path traversal is impossible by construction).

Keeping the two separate means a path-handling bug can never be driven by, or leak, the
secret capability.
"""

from __future__ import annotations

import secrets

_TOKEN_NBYTES = 32  # 256 bits
_STORED_NAME_NBYTES = 16  # 128 bits


def new_token() -> str:
    """Return a fresh URL-safe download capability token (>= 128 bits of entropy)."""
    return secrets.token_urlsafe(_TOKEN_NBYTES)


def new_stored_name() -> str:
    """Return a fresh random on-disk filename, distinct from any download token."""
    return secrets.token_hex(_STORED_NAME_NBYTES)
