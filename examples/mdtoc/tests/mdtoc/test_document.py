"""Markers + TOC builder — AC5, AC6, AC7 (doc half), AC8 (raise), AC10 (marker in fence).

``render`` behavior (idempotence, splice, exit codes) is covered in
``test_render_idempotence.py`` and ``test_cli.py``.
"""

import pytest

from mdtoc.document import (
    MalformedMarkersError,
    MissingMarkersError,
    build_toc,
    find_markers,
)
from mdtoc.headings import Heading

# --- find_markers -----------------------------------------------------------------


def test_find_markers_returns_indices():
    lines = "intro\n<!-- toc -->\n<!-- /toc -->\noutro".split("\n")
    assert find_markers(lines) == (1, 2)


def test_find_markers_tolerates_surrounding_whitespace():
    lines = "  <!-- toc -->  \n\t<!-- /toc -->".split("\n")
    assert find_markers(lines) == (0, 1)


def test_find_markers_missing_both_raises():
    with pytest.raises(MissingMarkersError):
        find_markers(["no markers here"])


def test_find_markers_missing_close_raises():
    with pytest.raises(MissingMarkersError):
        find_markers(["<!-- toc -->", "body without a close"])


def test_find_markers_close_before_open_raises():
    with pytest.raises(MalformedMarkersError):
        find_markers(["<!-- /toc -->", "<!-- toc -->"])


def test_find_markers_double_open_raises():
    with pytest.raises(MalformedMarkersError):
        find_markers(["<!-- toc -->", "<!-- toc -->", "<!-- /toc -->"])


def test_markers_inside_fence_ignored(golden):
    lines = golden("markers_in_fence.md").split("\n")
    open_i, close_i = find_markers(lines)
    assert lines[open_i].strip() == "<!-- toc -->"
    assert lines[close_i].strip() == "<!-- /toc -->"
    # The real markers sit AFTER the documentation fence; the fenced pair is ignored.
    fence_idx = next(i for i, line in enumerate(lines) if line.strip().startswith("```"))
    assert open_i > fence_idx


def test_find_markers_ignores_marker_in_mismatched_fence():
    # A ~~~ line inside a ``` block does not close it, so a <!-- toc --> line further
    # inside the block stays code and is not mistaken for the real marker.
    lines = [
        "# Doc",
        "```",
        "~~~",
        "<!-- toc -->",
        "```",
        "",
        "<!-- toc -->",
        "<!-- /toc -->",
        "## Usage",
    ]
    open_i, close_i = find_markers(lines)
    toc_opens = [i for i, line in enumerate(lines) if line.strip() == "<!-- toc -->"]
    assert open_i == toc_opens[-1]  # the real marker, not the fenced fake
    assert lines[close_i].strip() == "<!-- /toc -->"


# --- build_toc --------------------------------------------------------------------


def test_build_toc_nested_links_drops_leading_h1():
    headings = [
        Heading(1, "Title"),
        Heading(2, "Getting Started"),
        Heading(3, "Install"),
        Heading(2, "Usage"),
    ]
    assert build_toc(headings, 6) == (
        "- [Getting Started](#getting-started)\n" "  - [Install](#install)\n" "- [Usage](#usage)"
    )


def test_build_toc_empty_when_no_headings():
    assert build_toc([], 6) == ""


def test_build_toc_empty_when_only_leading_h1():
    assert build_toc([Heading(1, "Only Title")], 6) == ""


def test_leading_h1_skipped_only_first():
    # Only the first heading is dropped, and only because it is H1.
    assert build_toc([Heading(1, "Doc"), Heading(2, "A")], 6) == "- [A](#a)"


def test_second_h1_is_listed():
    headings = [Heading(1, "Doc"), Heading(1, "Chapter One"), Heading(2, "Section")]
    assert build_toc(headings, 6) == ("- [Chapter One](#chapter-one)\n  - [Section](#section)")


def test_build_toc_relative_indentation_when_starting_at_h2():
    headings = [Heading(2, "A"), Heading(3, "B"), Heading(2, "C")]
    # Shallowest kept level (H2) is column 0 — not over-indented.
    assert build_toc(headings, 6) == "- [A](#a)\n  - [B](#b)\n- [C](#c)"


def test_max_depth_filters_by_absolute_level():
    headings = [Heading(1, "T"), Heading(2, "A"), Heading(3, "B"), Heading(4, "C")]
    assert build_toc(headings, 2) == "- [A](#a)"
    assert build_toc(headings, 4) == ("- [A](#a)\n  - [B](#b)\n    - [C](#c)")


def test_duplicate_headings_get_distinct_anchors():
    headings = [Heading(2, "Overview"), Heading(2, "Overview"), Heading(2, "Setup")]
    assert build_toc(headings, 6) == ("- [Overview](#overview)\n" "- [Overview](#overview_1)\n" "- [Setup](#setup)")
