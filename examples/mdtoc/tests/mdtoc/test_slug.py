"""Slug fidelity — AC1 (slug half) and AC7 (duplicate disambiguation).

The slug string is mdtoc's public link contract, so these assert exact equality with
the Python-Markdown algorithm mdtoc replicates, including the ``_<n>`` anchored-regex
trap that a naive ``endswith`` check would get wrong.
"""

import pytest

from mdtoc.slug import slugify, unique_slug

try:
    from markdown.extensions.toc import slugify as md_slugify
    from markdown.extensions.toc import unique as md_unique

    HAS_MARKDOWN = True
except ImportError:  # pragma: no cover - exercised only when markdown is absent
    HAS_MARKDOWN = False


SLUG_CASES = [
    ("Hello World", "hello-world"),
    ("Café Menu", "cafe-menu"),  # NFKD drops the combining accent, not the whole word
    ("Foo: Bar!", "foo-bar"),  # punctuation stripped
    ("  Spaced   Out  ", "spaced-out"),  # trimmed + whitespace collapsed
    ("Already-hyphenated", "already-hyphenated"),
    ("Under_score kept", "under_score-kept"),  # underscore is a word char
    ("Section _2", "section-_2"),  # trailing _<n> survives slugify untouched
    ("", ""),  # empty heading text -> empty slug
    ("!!!", ""),  # all punctuation -> empty slug
]


@pytest.mark.parametrize("text, expected", SLUG_CASES)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_unique_slug_disambiguates_duplicates():
    used: set[str] = set()
    assert unique_slug("intro", used) == "intro"
    assert unique_slug("intro", used) == "intro_1"
    assert unique_slug("intro", used) == "intro_2"


def test_unique_slug_empty_becomes_underscore_one():
    used: set[str] = set()
    assert unique_slug("", used) == "_1"


def test_unique_slug_bumps_trailing_int_not_endswith():
    """A collision on ``section-_2`` must yield ``section-_3`` (bump), never ``section-_2_1``.

    This is the case a looser ``endswith('_<n>')`` shortcut would fail; it pins the
    anchored ``IDCOUNT_RE`` behavior.
    """
    used: set[str] = {"section-_2"}
    result = unique_slug("section-_2", used)
    assert result == "section-_3"
    assert result != "section-_2_1"


@pytest.mark.skipif(not HAS_MARKDOWN, reason="markdown package not installed")
@pytest.mark.parametrize("text, _expected", SLUG_CASES)
def test_slugify_matches_markdown(text, _expected):
    assert slugify(text) == md_slugify(text, "-")


@pytest.mark.skipif(not HAS_MARKDOWN, reason="markdown package not installed")
def test_unique_slug_matches_markdown():
    ours: set[str] = set()
    theirs: set[str] = set()
    for slug in ["intro", "intro", "intro", "section-_2", "section-_2", ""]:
        assert unique_slug(slug, ours) == md_unique(slug, theirs)
