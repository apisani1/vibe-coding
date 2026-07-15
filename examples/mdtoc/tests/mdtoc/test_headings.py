"""Heading scanner — AC10 (fenced code ignored) and the ATX rules from the design."""

from mdtoc.headings import Heading, parse_headings


def scan(text: str) -> list[Heading]:
    return parse_headings(text.split("\n"))


def test_all_atx_levels():
    text = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
    assert scan(text) == [
        Heading(1, "H1"),
        Heading(2, "H2"),
        Heading(3, "H3"),
        Heading(4, "H4"),
        Heading(5, "H5"),
        Heading(6, "H6"),
    ]


def test_requires_whitespace_after_hashes():
    assert scan("#NoSpace") == []
    assert scan("##AlsoNoSpace") == []


def test_more_than_six_hashes_is_not_a_heading():
    assert scan("####### Seven") == []


def test_leading_whitespace_in_text_trimmed():
    assert scan("##    Spaced Title") == [Heading(2, "Spaced Title")]


def test_closing_hashes_stripped():
    assert scan("## Foo ##") == [Heading(2, "Foo")]
    assert scan("### Bar ###   ") == [Heading(3, "Bar")]


def test_hash_inside_text_preserved():
    assert scan("## Issue #42 fixed") == [Heading(2, "Issue #42 fixed")]


def test_empty_heading_text():
    assert scan("## ") == [Heading(2, "")]


def test_backtick_fence_skipped():
    text = "## Real\n```\n# In Code\n```\n## After"
    assert scan(text) == [Heading(2, "Real"), Heading(2, "After")]


def test_tilde_fence_skipped():
    text = "## Real\n~~~\n# In Code\n~~~\n## After"
    assert scan(text) == [Heading(2, "Real"), Heading(2, "After")]


def test_info_string_fence_skipped():
    text = "## Real\n```python\n# comment not heading\n```\n## After"
    assert scan(text) == [Heading(2, "Real"), Heading(2, "After")]


def test_unterminated_fence_silently_omits_later_headings(golden):
    # data/unterminated_fence.md: one real H2, then an unclosed fence to EOF.
    headings = scan(golden("unterminated_fence.md"))
    assert headings == [Heading(1, "Title"), Heading(2, "Real Heading")]


def test_mismatched_fence_char_does_not_close_block():
    # A ~~~ line inside a ``` block is content, not a close, so the block stays open and
    # the heading inside it is not scanned.
    text = "## Real\n```\n~~~\n# In Code\n```\n## After"
    assert scan(text) == [Heading(2, "Real"), Heading(2, "After")]


def test_shorter_fence_does_not_close_longer_block():
    # A block opened with 4 backticks is only closed by 4+; a 3-backtick line is content.
    text = "## Real\n````\n```\n# In Code\n````\n## After"
    assert scan(text) == [Heading(2, "Real"), Heading(2, "After")]


def test_longer_fence_closes_shorter_block():
    # A block opened with 3 backticks is closed by a longer (4) run of the same char.
    text = "## Real\n```\n# In Code\n````\n## After"
    assert scan(text) == [Heading(2, "Real"), Heading(2, "After")]
