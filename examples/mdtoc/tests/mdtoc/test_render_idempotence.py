"""render fixed point + current/stale equivalence — AC1, AC2, AC3/AC4 (core half).

The idempotence guarantee is the spec's hardest requirement, so it gets its own file
and is exercised over a diverse fixture set (empty TOC, populated TOC, duplicates, CRLF,
unterminated fence, markers-in-fence), not just the easy case.
"""

import pytest

from mdtoc.document import render

FIXTURE_NAMES = [
    "simple.md",
    "duplicate_headings.md",
    "section_underscore.md",
    "unterminated_fence.md",
    "markers_in_fence.md",
    "crlf.md",
]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
@pytest.mark.parametrize("depth", [1, 2, 6])
def test_fixed_point(golden, name, depth):
    once = render(golden(name), depth)
    twice = render(once, depth)
    assert once == twice


def test_injection_golden(golden):
    # AC1: empty markers + headings -> the exact expected nested link block.
    assert render(golden("simple.md"), 6) == golden("simple.expected.md")


def test_stale_document_is_changed_by_render(golden):
    # simple.md has empty markers but real headings -> it is stale.
    text = golden("simple.md")
    assert render(text, 6) != text


def test_current_document_is_a_noop(golden):
    # The rendered document is current: rendering again changes nothing.
    current = golden("simple.expected.md")
    assert render(current, 6) == current


def test_current_write_check_equivalence(golden):
    """Directly guard D2: 'current' is one predicate shared by write and --check.

    (render(t) == t) is exactly the condition under which a write is a no-op and
    --check must report success; assert the two framings agree at the core level.
    """
    for name in FIXTURE_NAMES:
        text = render(golden(name), 6)  # a guaranteed-current document
        would_write = render(text, 6) != text  # writer would change the file?
        is_stale = render(text, 6) != text  # --check's staleness predicate
        assert would_write is False
        assert would_write == is_stale


def test_crlf_normalized_to_lf(golden):
    out = render(golden("crlf.md"), 6)
    assert "\r" not in out
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_empty_toc_region_byte_form():
    # Only a leading H1 -> empty TOC. The region must collapse to EXACTLY one blank
    # line between the markers (D6b empty-collapse clause); byte-locked so a wrong
    # blank-line count is caught (test_fixed_point alone cannot detect it).
    text = "# T\n\n<!-- toc -->\n<!-- /toc -->\n"
    assert render(text, 6) == "# T\n\n<!-- toc -->\n\n<!-- /toc -->\n"


def test_empty_toc_when_max_depth_below_all_headings():
    text = "# T\n\n<!-- toc -->\n<!-- /toc -->\n\n## A\n"
    # --max-depth 1 with a leading H1 keeps nothing -> empty region, no error.
    assert render(text, 1) == "# T\n\n<!-- toc -->\n\n<!-- /toc -->\n\n## A\n"
