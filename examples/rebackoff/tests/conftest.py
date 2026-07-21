"""Shared determinism seams: no test sleeps for real or reads a real clock/RNG."""

import pytest


class RecordingSleep:
    """A fake sync ``sleep`` that records each delay and returns immediately."""

    def __init__(self):
        self.calls = []

    def __call__(self, delay):
        self.calls.append(delay)


class FakeAsleep:
    """A fake async ``asleep`` that records each awaited delay without really waiting."""

    def __init__(self):
        self.calls = []

    async def __call__(self, delay):
        self.calls.append(delay)


class FakeClock:
    """A controllable monotonic clock. Advance it explicitly (or via ``ClockSleep``)."""

    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def advance(self, delta):
        self.now += delta


class ClockSleep:
    """Records delays AND advances a ``FakeClock`` — models time passing during a sleep."""

    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def __call__(self, delay):
        self.calls.append(delay)
        self.clock.advance(delay)


class AsyncClockSleep:
    """Async counterpart of ``ClockSleep``."""

    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    async def __call__(self, delay):
        self.calls.append(delay)
        self.clock.advance(delay)


@pytest.fixture
def recording_sleep():
    return RecordingSleep()


@pytest.fixture
def fake_asleep():
    return FakeAsleep()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def clock_sleep(clock):
    return ClockSleep(clock)


@pytest.fixture
def async_clock_sleep(clock):
    return AsyncClockSleep(clock)
