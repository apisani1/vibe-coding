import pytest

from shorturl import (
    codes,
    db,
)
from shorturl.api import create_app
from shorturl.config import Config

KEY = "secret"


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


def total_codes(config):
    conn = db.connect(config.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM codes").fetchone()[0]
    finally:
        conn.close()


def test_create_without_key_401_no_state_change(client, config):
    resp = client.post("/api/codes", json={"url": "https://a.com"})
    assert resp.status_code == 401
    assert total_codes(config) == 0


def test_create_with_wrong_key_403_no_state_change(client, config):
    resp = client.post("/api/codes", json={"url": "https://a.com"}, headers={"X-API-Key": "wrong"})
    assert resp.status_code == 403
    assert total_codes(config) == 0


def test_non_ascii_key_fails_closed_403(client, config):
    # A non-ASCII X-API-Key must return a clean 403, not a 500 from hmac.compare_digest.
    resp = client.post("/api/codes", json={"url": "https://a.com"}, headers={"X-API-Key": "kéy-ÿ"})
    assert resp.status_code == 403
    assert total_codes(config) == 0


def test_redirect_is_public_regardless_of_auth(client, config):
    # Seed a code directly, then hit the redirect with no key — it must still work.
    conn = db.connect(config.db_path)
    try:
        db.insert_code(
            conn,
            code="pub",
            target_url="https://example.com/x",
            created_at=codes.to_iso(codes.utcnow()),
            expires_at=None,
        )
    finally:
        conn.close()
    resp = client.get("/pub")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://example.com/x"
