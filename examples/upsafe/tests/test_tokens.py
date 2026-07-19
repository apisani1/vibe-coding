import re

from upsafe.tokens import new_stored_name, new_token

_URLSAFE = re.compile(r"^[A-Za-z0-9_-]+$")
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def test_token_is_urlsafe_and_high_entropy():
    token = new_token()
    assert _URLSAFE.match(token)
    # token_urlsafe(32) -> 43 chars of base64url; comfortably >= 128 bits.
    assert len(token) >= 43


def test_stored_name_is_128_bit_hex():
    assert _HEX32.match(new_stored_name())


def test_tokens_are_distinct_across_calls():
    assert len({new_token() for _ in range(100)}) == 100


def test_stored_names_are_distinct_across_calls():
    assert len({new_stored_name() for _ in range(100)}) == 100


def test_token_and_stored_name_differ():
    assert new_token() != new_stored_name()
