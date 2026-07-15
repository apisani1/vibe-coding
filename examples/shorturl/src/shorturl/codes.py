"""Pure domain helpers: code generation, input validation, time, and status.

Nothing here touches the database or the network — everything is a pure function of its
arguments, so it is trivially unit-testable and reusable by both the API and the CLI.
"""

from __future__ import annotations

import re
import secrets
from datetime import (
    datetime,
    timezone,
)
from typing import Literal
from urllib.parse import urlparse

# Auto-generated codes: base62, length 7 → 62^7 ≈ 3.5e12 (ample, non-enumerable).
CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
CODE_LENGTH = 7

# Custom aliases: base62 plus - and _, up to 64 chars. Kept distinct from the redirect
# route's reserved prefix so an alias can never collide with "/api/...".
_ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

Status = Literal["active", "expired", "deactivated"]


class InvalidURLError(ValueError):
    """The target URL is missing, malformed, or uses an unsupported scheme."""


class InvalidAliasError(ValueError):
    """The requested custom alias is not an allowed code string."""


class InvalidExpiryError(ValueError):
    """The supplied expiry timestamp is not a parseable ISO-8601 value."""


def generate_code(length: int = CODE_LENGTH) -> str:
    """Return a cryptographically-random base62 code of ``length`` characters."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def is_valid_alias(alias: str) -> bool:
    """Return True if ``alias`` is a well-formed custom code."""
    return bool(_ALIAS_RE.match(alias))


def validate_alias(alias: str) -> str:
    """Return ``alias`` unchanged, or raise ``InvalidAliasError``."""
    if not is_valid_alias(alias):
        raise InvalidAliasError("alias must be 1-64 chars of letters, digits, '-' or '_'")
    return alias


def validate_url(url: str) -> str:
    """Return the trimmed URL if it is a valid http(s) URL, else raise.

    Only ``http`` and ``https`` targets are accepted — the service redirects to whatever
    it is given, so schemes like ``javascript:`` or ``file:`` are rejected outright.
    """
    candidate = url.strip()
    if not candidate:
        raise InvalidURLError("url must not be empty")
    # Reject C0 control characters (incl. CR/LF/TAB) and DEL. urlparse silently strips these
    # when parsing, so without this check a URL like "https://h\r\nX: y" would validate but be
    # stored verbatim — later crashing the redirect's Location header (HTTP 500).
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        raise InvalidURLError("url must not contain control characters")
    # Require ASCII (RFC 3986): a non-ASCII codepoint (>0x7F) can't be latin-1-encoded into the
    # redirect Location header and would 500 at redirect time. Non-ASCII must be percent-encoded
    # or IDN-encoded (punycode) by the caller — both of which are ASCII.
    if not candidate.isascii():
        raise InvalidURLError("url must be ASCII (percent-encode or IDN-encode non-ASCII characters)")
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        raise InvalidURLError("url scheme must be http or https")
    if not parsed.netloc:
        raise InvalidURLError("url must include a host")
    return candidate


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    """Serialize a datetime to canonical ISO-8601 UTC text for storage."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat()


def normalize_expires_at(raw: str) -> str:
    """Parse a caller-supplied expiry string and return canonical ISO-8601 UTC text.

    A naive timestamp is interpreted as UTC. Raises ``InvalidExpiryError`` on anything
    ``datetime.fromisoformat`` cannot parse.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidExpiryError(f"expires_at is not a valid ISO-8601 timestamp: {raw!r}") from exc
    return to_iso(parsed)


def status(active: int, expires_at: str | None, now: datetime) -> Status:
    """Derive a code's three-way status.

    ``deactivated`` (manually expired via the CLI) is reported distinctly from
    ``expired`` (lapsed by TTL); the redirect gate treats both as non-serving.
    """
    if not active:
        return "deactivated"
    if expires_at is not None and datetime.fromisoformat(expires_at) <= now:
        return "expired"
    return "active"


def is_serving(active: int, expires_at: str | None, now: datetime) -> bool:
    """Return True only when a code should redirect (status is ``active``)."""
    return status(active, expires_at, now) == "active"
