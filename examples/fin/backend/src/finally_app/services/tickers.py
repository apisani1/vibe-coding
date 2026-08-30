"""The ticker format rule, in one place.

Three call sites need it and they must not disagree: the watchlist service, the
portfolio service, and the Pydantic models at the HTTP boundary. Two copies of a
regex that have to agree is the kind of thing that drifts silently — and this one
is a security guard, not only a UX one, because from CP9 the symbol can arrive
from model output rather than from a form.

**Validation lives in the service, not only at the boundary.** The chat
orchestrator calls the service functions directly (D5) and never constructs the
Pydantic model, so a rule enforced only in ``api/`` is not enforced on the path
that most needs it.

The pattern requires **at least one letter**. Without that lookahead,
``^[A-Z.\\-]{1,10}$`` accepts ``...`` and ``---``: junk that the simulator would
happily seed a price for the moment it entered the watchlist, at which point it
becomes tradeable.
"""

from __future__ import annotations

import re

# Either case at the boundary, because callers normalise rather than reject
# whitespace and lowercase (the design's rule for the watchlist).
TICKER_PATTERN = r"^(?=.*[A-Za-z])[A-Za-z.\-]{1,10}$"

_TICKER = re.compile(TICKER_PATTERN)


class InvalidTicker(ValueError):
    """A symbol that fails the format rule.

    A ``ValueError`` rather than a bespoke base class: it is a malformed value,
    and both the REST layer and the chat orchestrator want to say so plainly.
    """

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.reason = f"{raw!r} is not a valid ticker symbol"
        super().__init__(self.reason)


def normalise(raw: str) -> str:
    """Strip, upper-case, and validate. Returns the canonical symbol.

    Stripping happens *before* validation, so ``" aapl "`` normalises rather
    than being rejected — the design's "normalise, do not reject" rule. What is
    left must still be a plausible symbol.
    """
    candidate = raw.strip()
    if not _TICKER.match(candidate):
        raise InvalidTicker(raw)
    return candidate.upper()
