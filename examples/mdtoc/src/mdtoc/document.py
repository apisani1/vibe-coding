"""Document-level orchestration: marker location, TOC building, and (later) render.

Reuses the one fence model from :mod:`mdtoc.headings` (D5) so marker detection and
heading scanning never disagree. ``render`` is added in a later checkpoint; this
module currently provides the marker + TOC-building primitives it will compose.
"""

from mdtoc.headings import Heading, iter_code_free, parse_headings
from mdtoc.slug import slugify, unique_slug

TOC_OPEN = "<!-- toc -->"
TOC_CLOSE = "<!-- /toc -->"
INDENT_UNIT = "  "


class MdtocError(Exception):
    """Base class for expected, user-facing errors (mapped to CLI exit code 2)."""


class MissingMarkersError(MdtocError):
    """The document lacks a required ``<!-- toc -->`` / ``<!-- /toc -->`` marker."""


class MalformedMarkersError(MdtocError):
    """The markers are present but out of order (close-before-open, or a double open)."""


def find_markers(lines: list[str]) -> tuple[int, int]:
    """Return ``(open_index, close_index)`` of the first well-formed marker pair.

    Fence-aware: marker lines inside a fenced code block are ignored, so a document
    that merely *shows* the marker syntax (e.g. mdtoc's own README) is not managed.
    Raises :class:`MissingMarkersError` if a marker is absent and
    :class:`MalformedMarkersError` on close-before-open or a second open.
    """
    open_index: int | None = None
    for index, line in iter_code_free(lines):
        stripped = line.strip()
        if stripped == TOC_OPEN:
            if open_index is not None:
                raise MalformedMarkersError("second <!-- toc --> before <!-- /toc -->")
            open_index = index
        elif stripped == TOC_CLOSE:
            if open_index is None:
                raise MalformedMarkersError("<!-- /toc --> appears before <!-- toc -->")
            return open_index, index
    if open_index is None:
        raise MissingMarkersError("missing <!-- toc --> and <!-- /toc --> markers")
    raise MissingMarkersError("missing <!-- /toc --> marker")


def build_toc(headings: list[Heading], max_depth: int) -> str:
    """Render the TOC body (bullet lines joined by ``\\n``) for ``headings``.

    Drops a leading H1 document title (only the first heading, only if H1), keeps
    headings up to ``max_depth`` (absolute level), indents by relative depth in
    ``INDENT_UNIT`` units, and assigns unique slugs in document order. Returns an empty
    string when nothing is selected.
    """
    if headings and headings[0].level == 1:
        headings = headings[1:]
    kept = [h for h in headings if h.level <= max_depth]
    if not kept:
        return ""
    base = min(h.level for h in kept)
    used: set[str] = set()
    entries = []
    for heading in kept:
        slug = unique_slug(slugify(heading.text), used)
        indent = INDENT_UNIT * (heading.level - base)
        entries.append(f"{indent}- [{heading.text}](#{slug})")
    return "\n".join(entries)


def render(text: str, max_depth: int = 6) -> str:
    """Return ``text`` with the managed TOC region rewritten from its headings.

    This is a fixed point: ``render(render(text)) == render(text)``. A document is
    "current" iff ``render(text) == text`` — the property the CLI's write and
    ``--check`` paths both rely on. Line endings are normalized to LF and the output
    ends with exactly one trailing newline (D4). Headings are scanned only outside the
    marker region (D9) and the body is fenced by a single blank line on each side (D6b).
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    open_index, close_index = find_markers(lines)
    scan_lines = lines[:open_index] + lines[close_index + 1 :]
    body = build_toc(parse_headings(scan_lines), max_depth)
    middle = ["", *body.split("\n"), ""] if body else [""]
    new_lines = lines[: open_index + 1] + middle + lines[close_index:]
    return "\n".join(new_lines).rstrip("\n") + "\n"
