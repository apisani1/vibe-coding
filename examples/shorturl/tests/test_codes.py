from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pytest

from shorturl import codes


def test_generate_code_length_and_alphabet():
    code = codes.generate_code()
    assert len(code) == codes.CODE_LENGTH
    assert all(ch in codes.CODE_ALPHABET for ch in code)


def test_generate_code_custom_length():
    assert len(codes.generate_code(12)) == 12


def test_generate_code_varies():
    # Not a strict guarantee, but a collision here is astronomically unlikely.
    assert codes.generate_code() != codes.generate_code()


@pytest.mark.parametrize("alias", ["abc", "My-Link_1", "a", "A" * 64])
def test_valid_aliases(alias):
    assert codes.is_valid_alias(alias)
    assert codes.validate_alias(alias) == alias


@pytest.mark.parametrize("alias", ["", "has space", "bad/slash", "emoji😀", "A" * 65])
def test_invalid_aliases(alias):
    assert not codes.is_valid_alias(alias)
    with pytest.raises(codes.InvalidAliasError):
        codes.validate_alias(alias)


@pytest.mark.parametrize("url", ["http://example.com", "https://a.b/c?d=1", "  https://x.io/p  "])
def test_valid_urls(url):
    assert codes.validate_url(url) == url.strip()


@pytest.mark.parametrize("url", ["", "   ", "javascript:alert(1)", "ftp://x/y", "http://", "notaurl"])
def test_invalid_urls(url):
    with pytest.raises(codes.InvalidURLError):
        codes.validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com\r\nX-Test: injected",  # CRLF — would crash the Location header
        "https://example.com\tpath",  # tab
        "https://ex\x00ample.com",  # NUL
        "https://ex\x7fample.com",  # DEL
    ],
)
def test_control_characters_rejected(url):
    with pytest.raises(codes.InvalidURLError):
        codes.validate_url(url)


@pytest.mark.parametrize("url", ["https://exämple.com", "https://例え.com/path", "https://x.com/¤"])
def test_non_ascii_urls_rejected(url):
    # A non-ASCII codepoint would crash the latin-1 Location header at redirect time.
    with pytest.raises(codes.InvalidURLError):
        codes.validate_url(url)


@pytest.mark.parametrize("url", ["https://xn--mnchen-3ya.de", "https://x.com/%E2%9C%93"])
def test_ascii_encoded_urls_accepted(url):
    # The correct way to carry non-ASCII: IDN/punycode host or percent-encoded path (both ASCII).
    assert codes.validate_url(url) == url


def test_normalize_expires_at_roundtrips_utc():
    out = codes.normalize_expires_at("2030-01-02T03:04:05+00:00")
    assert out == "2030-01-02T03:04:05+00:00"


def test_normalize_expires_at_naive_is_utc():
    out = codes.normalize_expires_at("2030-01-02T03:04:05")
    assert out == "2030-01-02T03:04:05+00:00"


def test_normalize_expires_at_rejects_garbage():
    with pytest.raises(codes.InvalidExpiryError):
        codes.normalize_expires_at("not-a-date")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_status_active_without_expiry():
    now = codes.utcnow()
    assert codes.status(1, None, now) == "active"
    assert codes.is_serving(1, None, now) is True


def test_status_active_with_future_expiry():
    now = codes.utcnow()
    future = _iso(now + timedelta(hours=1))
    assert codes.status(1, future, now) == "active"


def test_status_expired_when_ttl_passed():
    now = codes.utcnow()
    past = _iso(now - timedelta(seconds=1))
    assert codes.status(1, past, now) == "expired"
    assert codes.is_serving(1, past, now) is False


def test_status_boundary_is_inclusive():
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert codes.status(1, _iso(now), now) == "expired"  # expires_at <= now


def test_status_deactivated_overrides_future_expiry():
    now = codes.utcnow()
    future = _iso(now + timedelta(days=1))
    assert codes.status(0, future, now) == "deactivated"
    assert codes.is_serving(0, future, now) is False
