"""Check A12 — env-driven source selection with no fallback, and fixture parsing.

The live Massive path cannot be verified here: MASSIVE_API_KEY is empty and the
account used previously returned 403 on /v2/snapshot. Everything below is what
IS checkable without a working key.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import httpx
import pytest

from finally_app.config import Settings
from finally_app.market import factory
from finally_app.market.massive import MassiveClient
from finally_app.market.simulator import Simulator

FIXTURES = Path(__file__).parent / "fixtures"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "openrouter_api_key": "",
        "openrouter_model": "",
        "massive_api_key": "",
        "massive_poll_seconds": 15.0,
        "llm_mock": True,
        "db_path": Path("unused.db"),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _client_returning(status: int, body: object = None) -> httpx.AsyncClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body if body is not None else {})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- selection ------------------------------------------------------------


def test_absent_key_selects_the_simulator() -> None:
    assert isinstance(factory.create_source(_settings()), Simulator)


def test_a_present_key_selects_massive() -> None:
    source = factory.create_source(_settings(massive_api_key="abc123"))

    # Exact type, not isinstance: a `class _ResilientMassive(MassiveClient)`
    # carrying a degrade path satisfies isinstance and was verified passing the
    # whole suite.
    assert type(source) is MassiveClient  # pylint: disable=unidiomatic-typecheck


def test_a_whitespace_only_key_is_treated_as_absent() -> None:
    """`MASSIVE_API_KEY=` with a stray space must not select the real API."""
    import os

    from finally_app.config import load_settings

    os.environ["MASSIVE_API_KEY"] = "   "
    try:
        assert not load_settings().use_massive
    finally:
        del os.environ["MASSIVE_API_KEY"]


def test_create_source_contains_no_error_handling_at_all() -> None:
    """D13, structural half — AST-based, not a string count.

    A fallback needs somewhere to catch the failure, so `create_source` having
    *any* try/except is the shape of the violation. The previous version of
    this check counted the literal string "Simulator" and was defeated by
    `from .simulator import Simulator as _Backup`; an AST walk cannot be
    dodged by renaming.
    """
    tree = ast.parse(inspect.getsource(factory))
    function = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "create_source"
    )

    assert not [
        n for n in ast.walk(function) if isinstance(n, (ast.Try, ast.ExceptHandler))
    ], "create_source contains exception handling — that is the shape a fallback takes"


def test_no_simulator_is_ever_constructed_while_a_massive_key_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D13, behavioural half — the assertion that actually matters.

    The earlier version only checked that *constructing* the client did not
    yield a Simulator. But D13's rejected alternative is "fall back to the
    simulator on repeated failure", which lives at **fetch** time: a
    `_degraded()` path inside `MassiveClient.fetch` returning simulated prices
    after N failures passed the entire suite while a 403 key served invented
    quotes. This tracks Simulator construction across the whole flow instead.
    """
    constructed: list[object] = []
    original_init = Simulator.__init__

    def spy_init(self: Simulator, *args: object, **kwargs: object) -> None:
        constructed.append(self)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Simulator, "__init__", spy_init)

    settings = _settings(massive_api_key="a-key-that-does-not-work")
    source = factory.create_source(settings)

    assert type(source) is MassiveClient  # pylint: disable=unidiomatic-typecheck
    assert not constructed, "a Simulator was built while a Massive key was configured"


SIMULATION_MODULES = ("simulator", "seed_prices")


@pytest.mark.parametrize("module_name", ["massive", "producer"])
def test_real_data_modules_cannot_import_the_simulator(module_name: str) -> None:
    """D13, provenance guard — the strongest of these, because it is unbounded.

    Every fallback the overseer built imported ``gbm_step`` or ``profile_for``
    directly rather than constructing a ``Simulator``, which made an
    ``__init__`` spy inert against all of them. Banning the import at module
    level catches the whole family at once: a real-data module that cannot see
    the simulation code cannot serve simulated prices, no matter how many
    failures it has counted or what class it wraps itself in.

    ``factory.py`` is deliberately exempt — selecting between the two sources is
    its entire job.
    """
    module = importlib.import_module(f"finally_app.market.{module_name}")
    tree = ast.parse(inspect.getsource(module))

    offending: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if any(part in SIMULATION_MODULES for part in node.module.split(".")):
                offending.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if any(part in SIMULATION_MODULES for part in alias.name.split(".")):
                    offending.append(f"import {alias.name}")

    assert not offending, (
        f"finally_app.market.{module_name} imports simulation code {offending} — "
        "a real-data module that can reach the simulator can serve invented prices (D13)"
    )


def test_the_client_returns_only_parsed_payload_or_nothing() -> None:
    """D13 at the *fetch* return boundary — the structural twin of the write guard.

    The write guard closes `producer.py`, but a degrade one module upstream —
    inside `MassiveClient.fetch`, gated on `asyncio.get_running_loop().time()` —
    slipped past it, past the clock ban (a `Call` receiver has no `.id`) and
    past payload provenance (400 polls of mock time never reach a 300 s gate).

    No count- or time-based test can bound that, for the same reason none could
    bound the producer variants. So constrain it structurally instead.

    **Scope, stated precisely rather than optimistically.** This asserts that
    every `return` in `fetch` is *syntactically* `{}` or a `parse_snapshot(...)`
    call. It checks the callee name, **not the provenance of the argument** — so
    `return parse_snapshot(self._degraded_payload())`, or a `carry` parameter
    added to `parse_snapshot` itself, still launders an invented number through.
    Those are deliberate laundering rather than the degrade sentence a developer
    writes, and they are recorded as adversarial residual risk in the build log
    rather than guarded here.

    What it does close is the natural family: a stored dict, a drifted copy, a
    comprehension, or a delegated `self._degraded()` — whatever triggered them.
    """
    module = importlib.import_module("finally_app.market.massive")
    tree = ast.parse(inspect.getsource(module))

    fetch = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "fetch")

    def describes_nothing(node: ast.expr | None) -> bool:
        return isinstance(node, ast.Dict) and not node.keys

    def describes_parsed_payload(node: ast.expr | None) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "parse_snapshot"

    offending = [
        ast.unparse(node.value) if node.value is not None else "None"
        for node in ast.walk(fetch)
        if isinstance(node, ast.Return)
        and not describes_nothing(node.value)
        and not describes_parsed_payload(node.value)
    ]

    assert not offending, (
        f"MassiveClient.fetch returns {offending} — every return must be `{{}}` or "
        "`parse_snapshot(...)`. Anything else is a price the transport never sent (D13)"
    )


def test_the_producer_writes_only_what_the_source_returned() -> None:
    """D13, the write-boundary guard — this is the one that covers the family.

    Every previous guard chased a *trigger*: a failure count, an elapsed time, a
    Simulator import. Each was escapable by changing the trigger — the overseer
    broke them with a >20 threshold, a subclass, `asyncio.get_running_loop().time()`,
    and finally `dead_polls * source.interval_seconds >= 300.0`, which reads no
    clock at all.

    But every fabrication in the family must eventually do the same thing: hand
    ``cache.apply`` a number ``source.fetch`` never returned. Guarding that one
    boundary covers all of them at once, and there is no trigger left to vary.

    Asserts, structurally: ``producer.py`` contains exactly one ``cache.apply``
    call site, and its argument is the bare name bound directly by
    ``await source.fetch(...)``.
    """
    module = importlib.import_module("finally_app.market.producer")
    tree = ast.parse(inspect.getsource(module))

    applies = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "apply"
    ]
    assert len(applies) == 1, (
        f"producer.py has {len(applies)} cache.apply call sites; a second one is where "
        "fabricated prices enter the cache (D13)"
    )

    call = applies[0]
    assert len(call.args) == 1 and not call.keywords, "cache.apply must take exactly the fetched prices"
    argument = call.args[0]
    assert isinstance(argument, ast.Name), (
        f"cache.apply is passed a {type(argument).__name__}, not a plain name — "
        "anything constructed at the call site is by definition not what the source returned"
    )

    fetched_names = {
        node.targets[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Await)
        and isinstance(node.value.value, ast.Call)
        and isinstance(node.value.value.func, ast.Attribute)
        and node.value.value.func.attr == "fetch"
    }
    assert argument.id in fetched_names, (
        f"cache.apply is passed '{argument.id}', which is not bound by await source.fetch(...) "
        f"(names that are: {sorted(fetched_names) or 'none'})"
    )

    # Checking the NAME alone is not enough: `prices = await source.fetch(t)` /
    # `prices = {fabricated}` / `cache.apply(prices)` keeps the name and swaps
    # the value, and so does `prices[t] = ...`. Immediate versions of both are
    # caught behaviourally by the cache-invariance test, but a version gated on
    # staleness would evade that too -- so pin it structurally as well: the
    # fetched name is bound exactly once and never mutated.
    name = argument.id
    rebinds = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]
    assert len(rebinds) == 1, (
        f"'{name}' is assigned {len(rebinds)} times; a second binding is where the fetched "
        "prices get swapped for fabricated ones while keeping the name"
    )

    subscript_writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AugAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == name
    ]
    assert not subscript_writes, f"'{name}' is written by subscript — that is fabrication in place"

    mutators = {"update", "setdefault", "pop", "popitem", "clear", "__setitem__"}
    in_place = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in mutators
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == name
    ]
    assert not in_place, f"'{name}' is mutated in place via {in_place} before reaching the cache"


CLOCK_READS = ("monotonic", "perf_counter", "time", "now", "utcnow")


@pytest.mark.parametrize("module_name", ["massive", "producer"])
def test_the_fetch_path_makes_no_freshness_decisions(module_name: str) -> None:
    """D13, unbounded — the guard that closes the time-gated fallback.

    A staleness-gated degrade ("no good tick in five minutes, keep the tape
    moving") is the most natural sentence a developer writes here, and no
    count-based test can bound it: it fires on elapsed time, so a test either
    waits five real minutes or misses it. Attempts to fake the clock backfire —
    patching ``time.monotonic`` also drives asyncio's event loop, which collapses
    the very window the test needs.

    So guard it structurally instead. **A fallback needs a clock to decide the
    feed is stale.** The fetch path has no legitimate reason to read one:
    timeouts are httpx's, cadence is the producer's ``interval_seconds``, and
    quote timestamps are stamped in ``cache.py``. Banning clock reads here makes
    the whole family unwritable rather than merely late-firing.
    """
    module = importlib.import_module(f"finally_app.market.{module_name}")
    tree = ast.parse(inspect.getsource(module))

    offending: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in CLOCK_READS:
            base = getattr(node.value, "id", "")
            if base in ("time", "datetime"):
                offending.append(f"{base}.{node.attr}")
        elif isinstance(node, ast.ImportFrom) and node.module in ("time", "datetime"):
            offending.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Import):
            offending.extend(a.name for a in node.names if a.name in ("time", "datetime"))

    assert not offending, (
        f"finally_app.market.{module_name} reads a clock {sorted(set(offending))} — "
        "a freshness decision in the fetch path is how a staleness-gated fallback is written (D13)"
    )


@pytest.mark.asyncio
async def test_every_price_returned_traces_to_the_payload_bytes() -> None:
    """D13, provenance — no threshold to outlast.

    Rather than asserting "no invented prices after N failures", assert that
    every price the client ever emits appears verbatim in the bytes the
    transport handed it.

    400 polls, up from 60, so a degrade must outlast a much larger failure
    budget. Measured shape: two successes, then 398 *consecutive* failures --
    `payloads` only grows on success, so the alternation stops once it does.
    That is what makes it strong against consecutive-failure gates, and it is
    worth stating precisely rather than describing it as 'alternating'.

    Time-gated and clock-free variants are closed by
    `test_the_producer_writes_only_what_the_source_returned`, not here.
    """
    payloads: list[dict[str, object]] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        # Two successes, then 403 forever: `payloads` only grows on success.
        if len(payloads) % 3 == 2:
            return httpx.Response(403, json={})
        body = {"tickers": [{"ticker": "AAPL", "lastTrade": {"p": 100.0 + len(payloads)}}]}
        payloads.append(body)
        return httpx.Response(200, json=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = factory.create_source(_settings(massive_api_key="k"))
    source._client = client  # type: ignore[attr-defined]  # pylint: disable=protected-access

    seen_prices: list[float] = []
    for _ in range(400):
        seen_prices.extend((await source.fetch(["AAPL"])).values())

    served = {
        entry["lastTrade"]["p"]  # type: ignore[index]
        for body in payloads
        for entry in body["tickers"]  # type: ignore[union-attr]
    }
    assert seen_prices, "the client never returned a price at all"
    for price in seen_prices:
        assert price in served, f"price {price} was never in any payload — it was invented"
    await client.aclose()


def test_poll_interval_comes_from_settings() -> None:
    """D24: a paid-tier user must be able to poll faster than the free-tier floor."""
    source = factory.create_source(_settings(massive_api_key="k", massive_poll_seconds=2.0))

    assert source.interval_seconds == 2.0


def test_poll_interval_defaults_to_fifteen_seconds() -> None:
    """The free tier is 5 calls/min, so 15s is the safe floor."""
    from finally_app.config import DEFAULT_MASSIVE_POLL_SECONDS, load_settings

    assert DEFAULT_MASSIVE_POLL_SECONDS == 15.0
    assert load_settings().massive_poll_seconds == 15.0
