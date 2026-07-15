import pytest

from shorturl import (
    codes,
    db,
)
from shorturl.api import create_app
from shorturl.cli import main
from shorturl.config import Config

KEY = "secret"
AUTH = {"X-API-Key": KEY}


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "s.db")
    monkeypatch.setenv("SHORTURL_DB", path)
    return path


@pytest.fixture()
def config(db_path):
    return Config(db_path=db_path, api_key=KEY, host="127.0.0.1", port=8000, base_url="http://sho.rt")


@pytest.fixture()
def client(config):
    return create_app(config).test_client()


def add_code(db_path, code, *, created_at="2026-04-01T12:00:00+00:00", expires_at=None, active=True, clicks=0):
    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        db.insert_code(
            conn,
            code=code,
            target_url=f"https://example.com/{code}",
            created_at=created_at,
            expires_at=expires_at,
        )
        for _ in range(clicks):
            db.insert_click(conn, code=code, clicked_at=codes.to_iso(codes.utcnow()), referer=None, user_agent=None)
        if not active:
            db.expire_code(conn, code)
    finally:
        conn.close()


def test_list_reflects_db(db_path, capsys):
    add_code(db_path, "alive", created_at="2026-04-01T12:00:00+00:00", clicks=2)
    add_code(db_path, "gone", active=False)
    add_code(db_path, "lapsed", expires_at="2000-01-01T00:00:00+00:00")
    rc = main(["list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "alive" in out and "active" in out
    assert "gone" in out and "deactivated" in out
    assert "lapsed" in out and "expired" in out
    # The "alive" row shows every AC #10 column: status, click count, created date,
    # expiry, and target.
    alive_line = next(line for line in out.splitlines() if line.startswith("alive"))
    assert "2" in alive_line
    assert "2026-04-01T12:00:00+00:00" in alive_line  # created date
    assert "https://example.com/alive" in alive_line  # target
    # An expiry date is rendered for a code that has one.
    lapsed_line = next(line for line in out.splitlines() if line.startswith("lapsed"))
    assert "2000-01-01T00:00:00+00:00" in lapsed_line
    # The header names the CREATED column.
    assert "CREATED" in out.splitlines()[0]


def test_expire_keeps_prior_clicks(db_path):
    # AC #8: expire deactivates but must NOT delete history (unlike delete, which cascades).
    add_code(db_path, "keep", clicks=3)
    assert main(["expire", "keep"]) == 0
    conn = db.connect(db_path)
    try:
        assert db.get_code(conn, "keep") is not None
        remaining = conn.execute("SELECT COUNT(*) FROM clicks WHERE code = 'keep'").fetchone()[0]
    finally:
        conn.close()
    assert remaining == 3


def test_list_empty(db_path, capsys):
    assert main(["list"]) == 0
    assert "no codes" in capsys.readouterr().out


def test_expire_makes_redirect_410(db_path, client, capsys):
    add_code(db_path, "e")
    assert main(["expire", "e"]) == 0
    assert "expired e" in capsys.readouterr().out
    # Shared store: the CLI expiry is visible to the HTTP redirect.
    assert client.get("/e").status_code == 410


def test_delete_removes_code_everywhere(db_path, client, capsys):
    add_code(db_path, "d", clicks=1)
    assert main(["delete", "d"]) == 0
    # Gone from the redirect...
    assert client.get("/d").status_code == 404
    # ...and gone from list.
    main(["list"])
    assert "d" not in [line.split()[0] for line in capsys.readouterr().out.splitlines()[1:]]


def test_expire_unknown_code_exits_nonzero(db_path, capsys):
    rc = main(["expire", "ghost"])
    assert rc == 1
    assert "no such code: ghost" in capsys.readouterr().err


def test_delete_unknown_code_exits_nonzero(db_path, capsys):
    rc = main(["delete", "ghost"])
    assert rc == 1
    assert "no such code: ghost" in capsys.readouterr().err


def test_shared_store_create_via_api_visible_to_cli(db_path, client, capsys):
    # AC #13 / R4: a code created over HTTP is seen by the CLI, and a CLI expiry is seen
    # by HTTP — proving both operate on the same SQLite file.
    resp = client.post("/api/codes", json={"url": "https://example.com/x", "alias": "shared"}, headers=AUTH)
    assert resp.status_code == 201
    main(["list"])
    assert "shared" in capsys.readouterr().out
    assert main(["expire", "shared"]) == 0
    assert client.get("/shared").status_code == 410
