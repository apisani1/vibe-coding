"""Type validation and outbound filename sanitization.

Two-layer, fail-closed acceptance:

- **Extension** must be on the configured allow-list (``check_extension``).
- **Content** must agree with that extension: binary types must start with a known
  magic-byte signature (``sniff_signature``); text types must be valid UTF-8 with no NUL
  or forbidden control bytes (``is_safe_text``). ``resolve_type`` combines both and
  returns the server-authoritative MIME type (never the client's declared one).

The text check is scoped to the inspected head buffer — the load-bearing guard is
"reject binary content masquerading as text", which its first bytes reveal. Inline
rendering is separately prevented by ``attachment`` + ``nosniff`` on download.

``content_disposition`` builds a header value that cannot be used to inject headers: a
stripped ASCII ``filename`` plus a percent-encoded RFC 5987 ``filename*``.
"""

from __future__ import annotations

import codecs
from typing import Mapping
from urllib.parse import quote

from .errors import TypeNotAllowed

# Extension -> acceptable magic-byte prefixes (binary types only).
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "pdf": (b"%PDF-",),
}
_TEXT_EXTS = frozenset({"txt", "csv"})

# C0 control bytes permitted in text content (tab, LF, CR); all other C0 + DEL forbidden.
_ALLOWED_TEXT_CONTROLS = frozenset({0x09, 0x0A, 0x0D})


def extract_extension(filename: str) -> str:
    """Lowercase extension of the basename, or '' if none. Never a path component."""
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in base:
        return ""
    return base.rsplit(".", 1)[-1].lower()


def check_extension(filename: str, allowed_types: Mapping[str, str]) -> str:
    ext = extract_extension(filename)
    if ext not in allowed_types:
        raise TypeNotAllowed(f"extension {ext!r} is not on the allow-list")
    return ext


def sniff_signature(ext: str, head: bytes) -> bool:
    """True if ``head`` matches ``ext``'s magic bytes. Text types have no signature (True)."""
    prefixes = _SIGNATURES.get(ext)
    if prefixes is None:
        return True
    return any(head.startswith(p) for p in prefixes)


def is_safe_text(data: bytes) -> bool:
    """True if ``data`` is valid UTF-8 with no NUL/forbidden control bytes."""
    for byte in data:
        if byte == 0x7F or (byte < 0x20 and byte not in _ALLOWED_TEXT_CONTROLS):
            return False
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        # final=False tolerates a multibyte char split at the head boundary; an actually
        # invalid sequence still raises.
        decoder.decode(data, final=False)
    except UnicodeDecodeError:
        return False
    return True


def resolve_type(ext: str, head: bytes, allowed_types: Mapping[str, str]) -> str:
    """Validate content against ``ext`` and return the server-side MIME type.

    Raises ``TypeNotAllowed`` if the extension is not allowed or the content does not
    match it.
    """
    if ext not in allowed_types:
        raise TypeNotAllowed(f"extension {ext!r} is not on the allow-list")
    if ext in _TEXT_EXTS:
        if not is_safe_text(head):
            raise TypeNotAllowed(f"content declared {ext!r} is not valid text")
    elif not sniff_signature(ext, head):
        raise TypeNotAllowed(f"content does not match the {ext!r} signature")
    return allowed_types[ext]


def content_disposition(original_name: str) -> str:
    """Build a safe ``Content-Disposition: attachment`` value (no header injection)."""
    ascii_name = "".join(ch for ch in original_name if 0x20 <= ord(ch) < 0x7F and ch not in '"\\/;')
    ascii_name = ascii_name.strip() or "download"
    encoded = quote(original_name, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"
