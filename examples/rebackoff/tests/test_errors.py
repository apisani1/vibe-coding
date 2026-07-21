"""RetryError carries the last exception and chains it as __cause__."""

from rebackoff.errors import RetryError


def test_retryerror_carries_metadata():
    orig = ValueError("boom")
    err = RetryError(last_exception=orig, attempts=3, elapsed=1.25)
    assert err.last_exception is orig
    assert err.attempts == 3
    assert err.elapsed == 1.25


def test_retryerror_message_mentions_attempts_and_last_error():
    err = RetryError(last_exception=ConnectionError("nope"), attempts=5, elapsed=2.0)
    text = str(err)
    assert "5 attempt" in text
    assert "ConnectionError" in text


def test_retryerror_chains_cause_when_raised_from():
    orig = TimeoutError("slow")
    try:
        raise RetryError(orig, attempts=2, elapsed=0.5) from orig
    except RetryError as err:
        assert err.__cause__ is orig
        assert err.last_exception is orig
