"""Checks A8, A9, A11 — the simulator's three properties that can silently break.

Each of these is calibrated so it can actually FAIL. A statistical test at
production tick parameters would pass under a broken implementation, which is
worse than no test at all.
"""

from __future__ import annotations

import math
import random
import statistics

from finally_app.market.simulator import (
    SECONDS_PER_TRADING_YEAR,
    SHOCK_MAX_MAGNITUDE,
    SHOCK_MIN_MAGNITUDE,
    SHOCK_RATE_PER_MINUTE,
    Simulator,
    gbm_step,
    shock_probability_per_tick,
)


def test_gbm_applies_the_jensen_correction() -> None:
    """A8: expected log return must be (mu - sigma^2/2)*dt, not mu*dt.

    Deliberately NOT at production parameters. At dt = 500ms of trading time
    and sigma ~2 the missing term shifts the price by a relative 1.7e-7, which
    needs ~10^7 samples to resolve and vanishes entirely under any rounding.
    Here: mu=0, sigma=1, dt=1 (one year), so the correct mean log return is
    -sigma^2/2 = -0.5 while the uncorrected form centres on 0.0. With n=4000
    the standard error is 1/sqrt(4000) ~ 0.0158, putting the two forms about 31
    standard errors apart.
    """
    rng = random.Random(1234)
    n = 4000
    log_returns = [math.log(gbm_step(100.0, 0.0, 1.0, 1.0, rng.gauss(0.0, 1.0)) / 100.0) for _ in range(n)]

    mean = statistics.fmean(log_returns)
    assert -0.55 < mean < -0.45, f"mean log return {mean!r} — the -sigma^2/2 term looks absent"


def test_gbm_step_is_pure_and_does_not_round() -> None:
    """The purity A8 depends on: same inputs, same output, full precision."""
    first = gbm_step(190.0, 0.1, 1.8, 1e-8, 0.5)
    second = gbm_step(190.0, 0.1, 1.8, 1e-8, 0.5)

    assert first == second
    # A rounding step inside would collapse this tiny move to exactly 190.0.
    assert first != 190.0


def test_shock_rate_conversion_is_per_minute_not_per_tick() -> None:
    """A9, part 1: the unit conversion itself."""
    assert shock_probability_per_tick(0.5, 0.01) == 0.01 * 0.5 / 60.0
    # The failure mode D23 names: treating the rate as per-tick would give 0.01
    # here, 120x too many shocks.
    assert shock_probability_per_tick(0.5, 0.01) < 0.001
    # And the shipped default is wired through, not just the helper in isolation.
    assert Simulator(tick_seconds=0.5).shock_probability == SHOCK_RATE_PER_MINUTE * 0.5 / 60.0


def test_shock_count_is_driven_by_advance_not_by_re_sampling() -> None:
    """A9, part 2: shocks actually fired, counted inside advance().

    The earlier version of this test sampled ``rng.random() <
    simulator.shock_probability`` in a loop and never called ``advance()``. That
    tested arithmetic, not the simulator: a subclass that never shocks and one
    that shocks every tick both passed it unchanged. Instrumenting real firings
    is the whole point.

    Horizon is 24 simulated hours rather than one. At 0.01/minute the hourly
    expectation is 0.6, so the plan's original ``0 < shocks < 3`` band was
    unreachable — a run with zero shocks is the single most likely outcome and
    would fail it about 55% of the time. Over 24 hours the expectation is ~14.4
    and a 5-30 band is comfortably inside the noise while still excluding both
    degenerate implementations.
    """
    ticks = 7200 * 24
    simulator = Simulator(tick_seconds=0.5, rng=random.Random(99))

    for _ in range(ticks):
        simulator.advance(["AAPL"])

    assert 5 <= simulator.shocks_fired <= 30, f"{simulator.shocks_fired} shocks over 24 simulated hours; expected ~14"


def test_the_shock_count_check_can_actually_fail() -> None:
    """Guard the guard: prove the band excludes both degenerate cases.

    A shock rate of zero and a rate high enough to fire constantly must both
    fall outside the band the test above asserts. Without this, a future change
    that disables shocks entirely would sail through.
    """
    ticks = 7200 * 24

    never = Simulator(tick_seconds=0.5, rng=random.Random(1), shock_rate_per_minute=0.0)
    for _ in range(ticks):
        never.advance(["AAPL"])
    assert never.shocks_fired == 0
    assert not 5 <= never.shocks_fired <= 30

    # 120/minute at a 0.5s tick is p=1.0 exactly; 60/minute would be p=0.5,
    # which fires ~500 times in 1000 ticks and would not pin the ceiling.
    always = Simulator(tick_seconds=0.5, rng=random.Random(1), shock_rate_per_minute=120.0)
    for _ in range(1000):
        always.advance(["AAPL"])
    assert always.shocks_fired == 1000
    assert not 5 <= always.shocks_fired <= 30


def _log_returns(series: list[float]) -> list[float]:
    return [math.log(b / a) for a, b in zip(series, series[1:])]


def test_correlated_tickers_co_move_and_uncorrelated_ones_do_not() -> None:
    """A11: the one-factor model's observable consequence.

    Shocks are disabled for this run. Correlation is a property of the
    *diffusion* term, and a single 2-5% jump dwarfs a window whose typical
    |log return| is ~8e-4 — with shocks on, the measured tech correlation
    ranges 0.30-0.77 across seeds against a >0.5 band, so the test would pass
    or fail on whether one outlier happened to land. Isolating the thing under
    test is what makes the bands meaningful rather than lucky.

    Bands are set from the measured distribution over 20 seeds, not guessed:
    tech 0.716-0.768 (theory 0.85*0.88 = 0.748) and cross 0.230-0.303 (theory
    0.85*0.30 = 0.255). A `cross < 0.3` band would therefore flake -- it sits
    inside the observed range. The load-bearing assertion is the *separation*:
    a broken one-factor model gives the two pairs the same correlation, or
    none at all, and either way the gap collapses.
    """
    tickers = ["AAPL", "MSFT", "JPM"]
    measured: list[tuple[float, float]] = []

    # Several seeds, so a single lucky stream cannot carry the assertion.
    for seed in (7, 11, 23, 101, 2024):
        simulator = Simulator(tick_seconds=0.5, rng=random.Random(seed), shock_rate_per_minute=0.0)
        series: dict[str, list[float]] = {t: [] for t in tickers}
        for _ in range(2000):
            prices = simulator.advance(tickers)
            for ticker in tickers:
                series[ticker].append(prices[ticker])

        aapl, msft, jpm = (_log_returns(series[t]) for t in tickers)
        measured.append((statistics.correlation(aapl, msft), statistics.correlation(aapl, jpm)))

    for tech, cross in measured:
        assert tech > 0.6, f"the tech block should co-move; got {tech:.3f}"
        assert cross < 0.4, f"JPM should drift largely on its own; got {cross:.3f}"
        assert tech - cross > 0.3, (
            f"tech {tech:.3f} and cross {cross:.3f} are too close — " "the market factor is not differentiating by rho"
        )


def test_dt_is_expressed_in_trading_time() -> None:
    """A calendar year here would understate volatility by ~4.5x."""
    assert SECONDS_PER_TRADING_YEAR == 252 * 6.5 * 3600


def test_unknown_tickers_still_get_a_price() -> None:
    """The spec allows adding any symbol; a row that never prices reads as a bug."""
    simulator = Simulator(rng=random.Random(1))
    prices = simulator.advance(["ZZZZ"])

    assert prices["ZZZZ"] > 0


def test_prices_stay_positive_across_a_long_run() -> None:
    simulator = Simulator(rng=random.Random(3))
    for _ in range(2000):
        prices = simulator.advance(["TSLA"])
        assert prices["TSLA"] > 0


# From SPEC.md section 6: "Occasional random 'events' -- sudden 2-5% moves on a
# ticker for drama". These literals are deliberately NOT imported from the
# simulator: asserting against SHOCK_MIN/MAX_MAGNITUDE would let a drift in
# those constants move both sides of the comparison together. Widening them to
# 0.20/0.50 -- ten times the spec -- passed the whole suite before this change.
SPEC_SHOCK_MIN = 0.02
SPEC_SHOCK_MAX = 0.05


def test_shock_magnitude_matches_the_spec_not_merely_its_own_constants() -> None:
    """Closes the coverage hole A11 opened by disabling shocks.

    A9 counts *firings* and asserts nothing about their size, and A11 now runs
    with shocks off — so without this, nothing checks the shipped shock
    behaviour at all. Exercises the shock step directly rather than diffing two
    simulators: the shocked and unshocked paths consume different numbers of
    RNG draws, so their price series are not comparable even from the same
    seed.
    """
    # The shipped constants must equal the spec's numbers. Without this, both
    # sides of the comparison below move together when a constant drifts.
    assert (SHOCK_MIN_MAGNITUDE, SHOCK_MAX_MAGNITUDE) == (SPEC_SHOCK_MIN, SPEC_SHOCK_MAX), (
        f"simulator constants {SHOCK_MIN_MAGNITUDE}/{SHOCK_MAX_MAGNITUDE} have drifted from "
        f"SPEC.md's {SPEC_SHOCK_MIN}/{SPEC_SHOCK_MAX}"
    )

    simulator = Simulator(tick_seconds=0.5, rng=random.Random(2024), shock_rate_per_minute=120.0)

    ups = downs = 0
    for _ in range(500):
        price, fired = simulator._maybe_shock(100.0)  # pylint: disable=protected-access
        assert fired, "p=1.0 must fire on every call"

        magnitude = abs(price / 100.0 - 1.0)
        assert (
            SPEC_SHOCK_MIN - 1e-9 <= magnitude <= SPEC_SHOCK_MAX + 1e-9
        ), f"shock magnitude {magnitude:.4%} outside the spec's 2-5% band"
        if price > 100.0:
            ups += 1
        else:
            downs += 1

    # Both directions must occur, or "sudden moves for drama" is a one-way ratchet.
    assert ups > 100 and downs > 100, f"shock direction is skewed: {ups} up / {downs} down"


def test_a_shock_moves_the_price_far_more_than_a_diffusion_step() -> None:
    """The premise D23 rests on: shocks punctuate the path, they do not blend into it."""
    simulator = Simulator(tick_seconds=0.5, rng=random.Random(5), shock_rate_per_minute=0.0)

    previous = simulator.advance(["AAPL"])["AAPL"]
    steps = []
    for _ in range(500):
        current = simulator.advance(["AAPL"])["AAPL"]
        steps.append(abs(current / previous - 1.0))  # consecutive, not cumulative
        previous = current
    typical_diffusion = statistics.median(steps)

    assert typical_diffusion < SPEC_SHOCK_MIN / 5, (
        f"a typical tick moves {typical_diffusion:.4%}, close to the {SPEC_SHOCK_MIN:.0%} "
        "shock floor — shocks would blend into the noise instead of punctuating it"
    )
