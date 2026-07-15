"""ATX heading scanning with fenced-code awareness.

A single pass over the document lines yields the ATX headings, skipping anything
inside a fenced code block. Fence tracking follows CommonMark closely enough to matter:
a code block opened with a run of ``` (or ~~~) is only closed by a fence of the *same*
character and *at least* the same length, so a ``~~~`` line inside a backtick block is
content, not a close. An unterminated fence leaves the scanner "in code" to the end of
input, silently omitting later headings — intended MVP behavior (see the design
edge-case table). Callers must exclude the managed ``<!-- toc -->`` region before
scanning so generated TOC bullets can never influence the fence state.
"""

import re
from typing import Iterator, NamedTuple, Optional

# ATX heading: 1-6 hashes, required whitespace, text, optional closing hashes.
ATX_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
# A fence line: a run of 3+ backticks or 3+ tildes at the start of the stripped line.
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# Open-fence state: (fence character, run length), or None when not inside a code block.
FenceState = Optional[tuple[str, int]]


class Heading(NamedTuple):
    """A parsed ATX heading: its level (1-6) and trimmed text."""

    level: int
    text: str


def fence_transition(line: str, fence: FenceState) -> FenceState:
    """Return the fenced-code state after ``line`` (``None`` outside a code block).

    Shared by heading scanning and marker detection so the two never disagree (D5).
    Opening: outside code, a run of 3+ ``` or ~~~ opens a block (info string ignored).
    Closing: inside code, a line whose whole stripped form is 3+ of the *same* character
    and at least the opening length. Any other fence-looking line inside code stays code.
    """
    stripped = line.strip()
    match = _FENCE_RE.match(stripped)
    if not match:
        return fence
    run = match.group(1)
    char, length = run[0], len(run)
    if fence is None:
        return (char, length)
    open_char, open_length = fence
    if char == open_char and length >= open_length and stripped == run:
        return None
    return fence


def iter_code_free(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Yield ``(index, line)`` for lines outside fenced code blocks.

    Fence lines (open/close) and everything between them are skipped. Shared by heading
    scanning and marker detection so both honor the one fence model (D5).
    """
    fence: FenceState = None
    for index, line in enumerate(lines):
        new_fence = fence_transition(line, fence)
        if new_fence != fence:  # this line opened or closed a fence
            fence = new_fence
            continue
        if fence is not None:  # inside a code block
            continue
        yield index, line


def parse_headings(lines: list[str]) -> list[Heading]:
    """Return the ATX headings in ``lines``, ignoring fenced code blocks."""
    headings: list[Heading] = []
    for _index, line in iter_code_free(lines):
        match = ATX_RE.match(line)
        if match:
            headings.append(Heading(len(match.group(1)), match.group(2)))
    return headings
