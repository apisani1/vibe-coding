from datetime import timedelta

import pytest

from upsafe.metadata import (
    StoredObject,
    connect,
    get_object,
    init_db,
    insert_object,
    utcnow,
)


@pytest.fixture()
def conn(tmp_path):
    connection = connect(tmp_path / "upsafe.db")
    init_db(connection)
    try:
        yield connection
    finally:
        connection.close()


def _obj(token="tok", stored_name="abc123", ttl_seconds=3600):
    now = utcnow()
    return StoredObject(
        token=token,
        stored_name=stored_name,
        original_name="photo.png",
        content_type="image/png",
        size=42,
        sha256="deadbeef",
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


def test_init_db_is_idempotent(conn):
    init_db(conn)  # second call must not raise
    init_db(conn)


def test_insert_then_get_round_trips(conn):
    obj = _obj()
    insert_object(conn, obj)
    fetched = get_object(conn, "tok")
    assert fetched is not None
    assert fetched.stored_name == "abc123"
    assert fetched.original_name == "photo.png"
    assert fetched.size == 42


def test_get_unknown_token_returns_none(conn):
    assert get_object(conn, "nope") is None


def test_get_expired_token_returns_none(conn):
    insert_object(conn, _obj(ttl_seconds=-1))  # already expired
    assert get_object(conn, "tok") is None


def test_expiry_boundary_is_exclusive(conn):
    obj = _obj(ttl_seconds=3600)
    insert_object(conn, obj)
    # exactly at expiry -> unavailable (<= now)
    assert get_object(conn, "tok", now=obj.expires_at) is None
    # one microsecond before -> available
    from datetime import timedelta as _td

    assert get_object(conn, "tok", now=obj.expires_at - _td(microseconds=1)) is not None


def test_duplicate_stored_name_rejected(conn):
    insert_object(conn, _obj(token="t1", stored_name="dup"))
    with pytest.raises(Exception):  # sqlite3.IntegrityError (UNIQUE)
        insert_object(conn, _obj(token="t2", stored_name="dup"))


def test_duplicate_token_rejected(conn):
    insert_object(conn, _obj(token="same", stored_name="s1"))
    with pytest.raises(Exception):  # sqlite3.IntegrityError (PRIMARY KEY)
        insert_object(conn, _obj(token="same", stored_name="s2"))
