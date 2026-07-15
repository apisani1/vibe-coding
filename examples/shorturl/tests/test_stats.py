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


def seed(config, code, *, expires_at=None, active=True, clicks=()):
    conn = db.connect(config.db_path)
    try:
        db.insert_code(
            conn,
            code=code,
            target_url="https://example.com/dest",
            created_at="2026-01-01T00:00:00+00:00",
            expires_at=expires_at,
        )
        for clicked_at, referer in clicks:
            db.insert_click(conn, code=code, clicked_at=clicked_at, referer=referer, user_agent="UA")
        if not active:
            db.expire_code(conn, code)
    finally:
        conn.close()


def test_stats_totals_series_and_referers(client, config):
    seed(
        config,
        "s",
        clicks=[
            ("2026-03-01T08:00:00+00:00", "https://a.com"),
            ("2026-03-01T09:00:00+00:00", "https://a.com"),
            ("2026-03-02T10:00:00+00:00", "https://b.com"),
            ("2026-03-02T11:00:00+00:00", None),
        ],
    )
    resp = client.get("/api/codes/s/stats", headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == "s"
    assert body["target_url"] == "https://example.com/dest"
    assert body["status"] == "active"
    assert body["total"] == 4
    # Two distinct UTC days, ordered ascending.
    assert body["series"] == [
        {"date": "2026-03-01", "count": 2},
        {"date": "2026-03-02", "count": 2},
    ]
    # NULL referer excluded; a.com (2) ranks above b.com (1).
    assert body["top_referers"] == [
        {"referer": "https://a.com", "count": 2},
        {"referer": "https://b.com", "count": 1},
    ]


def test_stats_reports_deactivated_status(client, config):
    seed(config, "dead", active=False)
    body = client.get("/api/codes/dead/stats", headers=AUTH).get_json()
    assert body["status"] == "deactivated"
    assert body["total"] == 0
    assert body["series"] == []
    assert body["top_referers"] == []


def test_stats_reports_expired_status(client, config):
    seed(config, "old", expires_at="2000-01-01T00:00:00+00:00")
    body = client.get("/api/codes/old/stats", headers=AUTH).get_json()
    assert body["status"] == "expired"


def test_stats_unknown_code_404(client, config):
    resp = client.get("/api/codes/missing/stats", headers=AUTH)
    assert resp.status_code == 404


def test_stats_requires_auth(client, config):
    seed(config, "s", clicks=[("2026-03-01T08:00:00+00:00", None)])
    assert client.get("/api/codes/s/stats").status_code == 401
    assert client.get("/api/codes/s/stats", headers={"X-API-Key": "wrong"}).status_code == 403
