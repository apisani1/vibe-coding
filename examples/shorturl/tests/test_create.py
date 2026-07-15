import pytest

from shorturl import (
    codes,
    db,
)
from shorturl.api import create_app
from shorturl.config import Config

KEY = "secret"
AUTH = {"X-API-Key": KEY}


@pytest.fixture()
def config(tmp_path):
    return Config(
        db_path=str(tmp_path / "s.db"),
        api_key=KEY,
        host="127.0.0.1",
        port=8000,
        base_url="http://sho.rt",
    )


@pytest.fixture()
def client(config):
    return create_app(config).test_client()


def code_count(config, code):
    conn = db.connect(config.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM codes WHERE code = ?", (code,)).fetchone()[0]
    finally:
        conn.close()


def total_codes(config):
    conn = db.connect(config.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM codes").fetchone()[0]
    finally:
        conn.close()


def test_create_auto_code_201(client, config):
    resp = client.post("/api/codes", json={"url": "https://example.com/page"}, headers=AUTH)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["code"]
    assert all(ch in codes.CODE_ALPHABET for ch in body["code"])
    assert body["short_url"] == f"http://sho.rt/{body['code']}"
    assert body["target_url"] == "https://example.com/page"
    assert code_count(config, body["code"]) == 1


def test_create_custom_alias_201(client, config):
    resp = client.post("/api/codes", json={"url": "https://example.com", "alias": "my-link"}, headers=AUTH)
    assert resp.status_code == 201
    assert resp.get_json()["code"] == "my-link"
    assert code_count(config, "my-link") == 1


def test_duplicate_alias_409_no_dup(client, config):
    first = client.post("/api/codes", json={"url": "https://a.com", "alias": "dup"}, headers=AUTH)
    assert first.status_code == 201
    second = client.post("/api/codes", json={"url": "https://b.com", "alias": "dup"}, headers=AUTH)
    assert second.status_code == 409
    assert code_count(config, "dup") == 1


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://x/y", "", "notaurl"])
def test_malformed_url_400_no_row(client, config, url):
    resp = client.post("/api/codes", json={"url": url}, headers=AUTH)
    assert resp.status_code == 400
    assert total_codes(config) == 0


def test_missing_url_400(client, config):
    resp = client.post("/api/codes", json={"alias": "x"}, headers=AUTH)
    assert resp.status_code == 400
    assert total_codes(config) == 0


def test_non_json_body_400(client, config):
    resp = client.post("/api/codes", data="not json", content_type="text/plain", headers=AUTH)
    assert resp.status_code == 400


def test_crlf_in_url_rejected_400_no_row(client, config):
    # A URL with embedded CR/LF must be rejected at create time (AC #4), not stored and then
    # 500 the public redirect via the Location header.
    resp = client.post("/api/codes", json={"url": "https://example.com\r\nX-Test: injected"}, headers=AUTH)
    assert resp.status_code == 400
    assert total_codes(config) == 0


def test_non_ascii_url_rejected_400_no_row(client, config):
    # Closes the same malformed-URL->redirect-500 class as the CRLF case, for high codepoints.
    resp = client.post("/api/codes", json={"url": "https://例え.com"}, headers=AUTH)
    assert resp.status_code == 400
    assert total_codes(config) == 0


def test_bad_alias_400(client, config):
    resp = client.post("/api/codes", json={"url": "https://a.com", "alias": "has space"}, headers=AUTH)
    assert resp.status_code == 400
    assert total_codes(config) == 0


def test_bad_expires_at_400(client, config):
    resp = client.post("/api/codes", json={"url": "https://a.com", "expires_at": "nope"}, headers=AUTH)
    assert resp.status_code == 400
    assert total_codes(config) == 0


def test_expires_at_normalized_and_stored(client, config):
    resp = client.post(
        "/api/codes",
        json={"url": "https://a.com", "alias": "exp", "expires_at": "2030-06-01T12:00:00"},
        headers=AUTH,
    )
    assert resp.status_code == 201
    assert resp.get_json()["expires_at"] == "2030-06-01T12:00:00+00:00"
    row = None
    conn = db.connect(config.db_path)
    try:
        row = db.get_code(conn, "exp")
    finally:
        conn.close()
    assert row["expires_at"] == "2030-06-01T12:00:00+00:00"
