import sqlite3
import threading

import pytest

from shorturl import (
    codes,
    db,
)
from shorturl.api import create_app
from shorturl.config import Config


@pytest.fixture()
def config(tmp_path):
    return Config(
        db_path=str(tmp_path / "s.db"),
        api_key=None,
        host="127.0.0.1",
        port=8000,
        base_url="http://sho.rt",
    )


@pytest.fixture()
def client(config):
    return create_app(config).test_client()


def add_code(config, code, *, url="https://example.com/dest", expires_at=None, active=True):
    conn = db.connect(config.db_path)
    try:
        db.insert_code(
            conn,
            code=code,
            target_url=url,
            created_at=codes.to_iso(codes.utcnow()),
            expires_at=expires_at,
        )
        if not active:
            db.expire_code(conn, code)
    finally:
        conn.close()


def clicks_for(config, code):
    conn = db.connect(config.db_path)
    try:
        return conn.execute("SELECT referer, user_agent FROM clicks WHERE code = ?", (code,)).fetchall()
    finally:
        conn.close()


def test_active_code_redirects_302_and_records_one_click(client, config):
    add_code(config, "abc", url="https://example.com/dest")
    resp = client.get("/abc", headers={"Referer": "https://ref.example", "User-Agent": "pytest-agent"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://example.com/dest"
    rows = clicks_for(config, "abc")
    assert len(rows) == 1
    assert rows[0]["referer"] == "https://ref.example"
    assert rows[0]["user_agent"] == "pytest-agent"


def test_click_without_headers_stores_null(client, config):
    add_code(config, "noh")
    resp = client.get("/noh")
    assert resp.status_code == 302
    rows = clicks_for(config, "noh")
    assert rows[0]["referer"] is None


def test_unknown_code_404_and_no_click(client, config):
    resp = client.get("/missing")
    assert resp.status_code == 404
    assert clicks_for(config, "missing") == []


def test_ttl_expired_code_410_and_no_click(client, config):
    past = codes.to_iso(codes.utcnow().replace(year=2000))
    add_code(config, "old", expires_at=past)
    resp = client.get("/old")
    assert resp.status_code == 410
    assert clicks_for(config, "old") == []


def test_deactivated_code_410_and_no_click(client, config):
    add_code(config, "dead", active=False)
    resp = client.get("/dead")
    assert resp.status_code == 410
    assert clicks_for(config, "dead") == []


def test_api_path_is_not_swallowed_by_redirect_route(client, config):
    # A multi-segment /api/... path must not be captured by the single-segment /<code>
    # route (R2). Whatever the exact status (the /api/* auth gate returns 401 here; a
    # missing route would be 404), it must never be a redirect — that would mean /<code>
    # had swallowed the path.
    resp = client.get("/api/codes/abc/stats")
    assert resp.status_code != 302
    assert resp.headers.get("Location") is None


def test_redirect_404_if_code_deleted_between_lookup_and_click(client, config, monkeypatch):
    # TOCTOU race: the code is deleted (FK cascade) after the redirect handler read it but
    # before the click insert. The FK IntegrityError must become a clean 404, not a 500.
    add_code(config, "race")

    def raise_fk(*_args, **_kwargs):
        raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")

    monkeypatch.setattr("shorturl.db.insert_click", raise_fk)
    resp = client.get("/race")
    assert resp.status_code == 404


def test_concurrent_click_inserts_all_land(config):
    # R1: connection-per-writer + WAL + busy_timeout should let concurrent inserts through
    # on a real file DB without OperationalError. Best-effort local check.
    schema_conn = db.connect(config.db_path)
    db.init_schema(schema_conn)
    schema_conn.close()
    add_code(config, "hot")
    errors: list[Exception] = []

    def hit():
        try:
            conn = db.connect(config.db_path)
            db.insert_click(
                conn,
                code="hot",
                clicked_at=codes.to_iso(codes.utcnow()),
                referer=None,
                user_agent=None,
            )
            conn.close()
        except Exception as exc:  # noqa: BLE001 - the point is to surface any DB error
            errors.append(exc)

    threads = [threading.Thread(target=hit) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(clicks_for(config, "hot")) == 20
