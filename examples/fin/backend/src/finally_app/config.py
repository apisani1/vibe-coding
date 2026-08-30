"""Environment configuration, read once into an immutable value object.

Every module takes ``Settings`` as a parameter rather than reaching for
``os.environ`` itself. That is what keeps the whole backend testable without
monkeypatching the process environment.

Validation is deliberately fail-soft: a missing LLM key does not stop the
process, because someone who only wants to watch prices and trade should not be
blocked by a credential they never intend to use. The chat endpoint reports the
problem instead, naming the variable it needs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path("db/finally.db")

# Hosts this application will answer for.
#
# Without a check, `Host: evil.example.com` returns 200 — verified — and that is
# what makes DNS rebinding work: an attacker's page re-resolves its own domain
# to 127.0.0.1, becomes **same-origin** with a no-auth app, and the (correct)
# absence of CORS is never consulted. It can then read the portfolio and the
# whole chat transcript, trade, and drive `/api/chat` in a loop at real cost.
#
# Test scaffolding does **not** live here: the suite's own hosts (`test`,
# `testserver` — httpx's and Starlette's ASGI defaults) are set by the test
# fixture instead, so the shipped default carries nothing a production process
# does not need. Anything else — a container service name, a LAN hostname —
# goes in ALLOWED_HOSTS.
#
# `[::1]` is kept for documentation rather than effect: Starlette matches on
# `host.split(":")[0]`, so an IPv6 `Host: [::1]:8000` arrives as `[` and can
# never match. Both start scripts publish IPv4 loopback, so nothing sends it.
DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "[::1]")

# The fallback poll interval, not the validated one. `MASSIVE_POLL_SECONDS` is
# range-checked in `market/massive.py`'s `valid_poll_seconds`, at the one place
# that turns the number into a sleep — `0`, `-5`, `inf` and `nan` all parse as
# floats and each breaks the producer differently. Validating here instead would
# repeat CP9's mistake: a rule in the loader is invisible to every caller that
# constructs `MassiveClient` directly.
DEFAULT_MASSIVE_POLL_SECONDS = 15.0


def _env(name: str, default: str = "") -> str:
    """Read an environment variable, treating whitespace-only as unset."""
    return os.environ.get(name, default).strip()


def _hosts() -> tuple[str, ...]:
    """`ALLOWED_HOSTS` as a tuple, or the defaults when unset."""
    raw = _env("ALLOWED_HOSTS")
    if not raw:
        return DEFAULT_ALLOWED_HOSTS
    return tuple(host.strip() for host in raw.split(",") if host.strip())


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable, falling back on absent or unparseable values."""
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the process environment."""

    openrouter_api_key: str
    openrouter_model: str
    massive_api_key: str
    massive_poll_seconds: float
    llm_mock: bool
    db_path: Path
    # Defaulted so that every test constructing `Settings` explicitly — there are
    # a hundred — keeps working, and so that the safe list is the one you get
    # unless you deliberately widen it.
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_HOSTS

    @property
    def use_massive(self) -> bool:
        """True when real market data was requested.

        A key that is present but broken still selects Massive: falling back to
        the simulator would show someone plausible invented prices while they
        believe they are looking at the market.
        """
        return bool(self.massive_api_key)

    @property
    def llm_configured(self) -> bool:
        """True when a live LLM call could be attempted."""
        return bool(self.openrouter_api_key and self.openrouter_model)


def load_settings() -> Settings:
    """Build ``Settings`` from the current environment."""
    return Settings(
        openrouter_api_key=_env("OPENROUTER_API_KEY"),
        openrouter_model=_env("OPENROUTER_MODEL"),
        massive_api_key=_env("MASSIVE_API_KEY"),
        massive_poll_seconds=_env_float("MASSIVE_POLL_SECONDS", DEFAULT_MASSIVE_POLL_SECONDS),
        llm_mock=_env("LLM_MOCK").lower() == "true",
        # Deliberately NOT read from the environment. Tests inject `db_path`
        # directly when constructing Settings, so an env read bought nothing
        # except a seventh, undocumented variable — and the documented surface
        # is exactly the six in .env.example, which check GD4 holds us to.
        #
        # This comment said "a sixth ... exactly the five" until CP18 added
        # ALLOWED_HOSTS, and then said "a sixth ... exactly the six" for the
        # length of one commit, because CP21 updated one number and not the
        # ordinal beside it. Two counts in one sentence is how that happens;
        # GD4 compares variable *names* and passed throughout, so nothing
        # automated was ever going to catch either version.
        db_path=DEFAULT_DB_PATH,
        allowed_hosts=_hosts(),
    )
