"""Heading-to-anchor slugging, faithful to Python-Markdown's ``toc`` extension.

Rather than depend on the ``markdown`` package at runtime, mdtoc replicates its
default ``slugify`` and collision-disambiguation (``unique``) so anchors resolve in
MkDocs/Sphinx-style renderers. Behavior is pinned by the project's own tests (and an
optional dev-only cross-check against the real ``markdown`` package).
"""

import re
import unicodedata

# Python-Markdown's toc.unique() suffix pattern: a trailing ``_<int>`` is bumped, so a
# collision on ``foo_2`` yields ``foo_3`` (not ``foo_2_1``). The anchor is significant.
IDCOUNT_RE = re.compile(r"(.*)_([0-9]+)$")


def slugify(text: str, separator: str = "-") -> str:
    """Return the anchor slug for a heading, matching Python-Markdown (``unicode=False``).

    Normalize to NFKD and drop non-ASCII, remove every character that is not a word
    char / whitespace / hyphen, lowercase, then collapse runs of whitespace and the
    separator into a single separator.
    """
    value = unicodedata.normalize("NFKD", text)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(rf"[{re.escape(separator)}\s]+", separator, value)


def unique_slug(slug: str, used: set[str]) -> str:
    """Disambiguate ``slug`` against ``used``, matching Python-Markdown's ``unique()``.

    While the slug is already taken (or empty), bump a trailing ``_<int>`` if present
    else append ``_1``. The chosen slug is added to ``used`` and returned.
    """
    while slug in used or not slug:
        match = IDCOUNT_RE.match(slug)
        if match:
            slug = f"{match.group(1)}_{int(match.group(2)) + 1}"
        else:
            slug = f"{slug}_1"
    used.add(slug)
    return slug
