import sqlite3

import pytest

from shorturl import db


@pytest.fixture()
def conn():
    connection = db.connect(":memory:")
    db.init_schema(connection)
    yield connection
    connection.close()


def _add(connection, code="abc", url="https://example.com", created_at="2026-01-01T00:00:00+00:00", expires_at=None):
    db.insert_code(connection, code=code, target_url=url, created_at=created_at, expires_at=expires_at)


def test_insert_and_get_roundtrip(conn):
    _add(conn, code="abc", url="https://example.com/x", expires_at="2030-01-01T00:00:00+00:00")
    row = db.get_code(conn, "abc")
    assert row is not None
    assert row["target_url"] == "https://example.com/x"
    assert row["active"] == 1
    assert row["expires_at"] == "2030-01-01T00:00:00+00:00"


def test_get_code_missing_returns_none(conn):
    assert db.get_code(conn, "nope") is None


def test_duplicate_code_raises_integrity_error(conn):
    # This UNIQUE guarantee is what the auto-generation retry loop relies on (R6).
    _add(conn, code="dup")
    with pytest.raises(sqlite3.IntegrityError):
        _add(conn, code="dup", url="https://other.example")


def test_expire_code_deactivates(conn):
    _add(conn, code="e")
    assert db.expire_code(conn, "e") is True
    assert db.get_code(conn, "e")["active"] == 0


def test_expire_missing_returns_false(conn):
    assert db.expire_code(conn, "ghost") is False


def test_delete_cascades_clicks(conn):
    _add(conn, code="d")
    db.insert_click(conn, code="d", clicked_at="2026-01-01T00:00:00+00:00", referer=None, user_agent=None)
    assert db.delete_code(conn, "d") is True
    assert db.get_code(conn, "d") is None
    # R5: foreign_keys=ON makes the click cascade away with its code.
    remaining = conn.execute("SELECT COUNT(*) FROM clicks WHERE code = 'd'").fetchone()[0]
    assert remaining == 0


def test_delete_missing_returns_false(conn):
    assert db.delete_code(conn, "ghost") is False


def test_list_codes_reports_click_count_newest_first(conn):
    _add(conn, code="old", created_at="2026-01-01T00:00:00+00:00")
    _add(conn, code="new", created_at="2026-02-01T00:00:00+00:00")
    for _ in range(3):
        db.insert_click(conn, code="new", clicked_at="2026-02-02T00:00:00+00:00", referer=None, user_agent=None)
    rows = db.list_codes(conn)
    assert [r["code"] for r in rows] == ["new", "old"]
    counts = {r["code"]: r["click_count"] for r in rows}
    assert counts == {"new": 3, "old": 0}


def test_get_stats_buckets_by_day_and_ranks_referers(conn):
    _add(conn, code="s")
    seed = [
        ("2026-03-01T08:00:00+00:00", "https://a.com"),
        ("2026-03-01T09:00:00+00:00", "https://a.com"),
        ("2026-03-02T10:00:00+00:00", "https://b.com"),
        ("2026-03-02T11:00:00+00:00", None),
    ]
    for clicked_at, referer in seed:
        db.insert_click(conn, code="s", clicked_at=clicked_at, referer=referer, user_agent="UA")
    stats = db.get_stats(conn, "s")
    assert stats["total"] == 4
    # Two distinct UTC days, ordered.
    assert stats["series"] == [
        {"date": "2026-03-01", "count": 2},
        {"date": "2026-03-02", "count": 2},
    ]
    # NULL referer excluded; a.com (2) ranks above b.com (1).
    assert stats["top_referers"] == [
        {"referer": "https://a.com", "count": 2},
        {"referer": "https://b.com", "count": 1},
    ]


def test_get_stats_empty_code(conn):
    _add(conn, code="empty")
    stats = db.get_stats(conn, "empty")
    assert stats == {"total": 0, "series": [], "top_referers": []}
