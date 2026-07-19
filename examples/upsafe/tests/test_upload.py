import hashlib
import io
import logging

import pytest
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartException

from upsafe.app import create_app
from upsafe.config import load_settings
from upsafe.logging import LOGGER_NAME
from upsafe.metadata import connect
from upsafe.routes import _too_large_or_bad_request


def _capture_logs():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    return buf, handler, logger


API_KEY = "test-key"
MAX_BYTES = 4096
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
SCRIPT = b"#!/bin/sh\nrm -rf /\n"


@pytest.fixture()
def settings(tmp_path):
    return load_settings(
        env={
            "UPSAFE_API_KEY": API_KEY,
            "UPSAFE_DATA_ROOT": str(tmp_path),
            "UPSAFE_MAX_UPLOAD_BYTES": str(MAX_BYTES),
        }
    )


@pytest.fixture()
def client(settings):
    return TestClient(create_app(settings))


def _published(settings):
    return [p for p in settings.quarantine_dir.iterdir() if not p.name.startswith(".tmp-")]


def _row_count(settings):
    conn = connect(settings.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    finally:
        conn.close()


def test_happy_path_returns_token_and_metadata(client, settings):
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("photo.png", PNG, "image/png")})
    assert resp.status_code == 201
    body = resp.json()
    assert body["token"]
    assert body["original_name"] == "photo.png"
    assert body["content_type"] == "image/png"
    assert body["size"] == len(PNG)
    assert body["sha256"] == hashlib.sha256(PNG).hexdigest()
    assert len(_published(settings)) == 1
    assert _row_count(settings) == 1


def test_missing_key_rejected_and_nothing_persisted(client, settings):
    resp = client.post("/uploads", files={"file": ("photo.png", PNG, "image/png")})
    assert resp.status_code == 401
    assert _published(settings) == []
    assert _row_count(settings) == 0


def test_wrong_key_rejected(client):
    resp = client.post("/uploads", headers={"X-API-Key": "nope"}, files={"file": ("photo.png", PNG, "image/png")})
    assert resp.status_code == 401


def test_oversize_rejected_mid_stream_no_residue(client, settings):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_BYTES * 2)
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("big.png", big, "image/png")})
    assert resp.status_code == 413
    assert _published(settings) == []
    assert _row_count(settings) == 0


def test_disallowed_extension_rejected(client, settings):
    resp = client.post(
        "/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("evil.exe", PNG, "application/octet-stream")}
    )
    assert resp.status_code == 415
    assert _published(settings) == []
    assert _row_count(settings) == 0


def test_bad_magic_rejected(client, settings):
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("photo.png", SCRIPT, "image/png")})
    assert resp.status_code == 415
    assert _published(settings) == []
    assert _row_count(settings) == 0


def test_empty_file_rejected(client, settings):
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("empty.png", b"", "image/png")})
    assert resp.status_code == 400
    assert _published(settings) == []


def test_no_file_part_rejected(client):
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, data={"notafile": "x"})
    assert resp.status_code == 400


def test_multiple_file_parts_rejected(client, settings):
    resp = client.post(
        "/uploads",
        headers={"X-API-Key": API_KEY},
        files=[("file", ("a.png", PNG, "image/png")), ("file2", ("b.png", PNG, "image/png"))],
    )
    assert resp.status_code == 400
    assert _published(settings) == []


# R-1: the 413-vs-400 split couples to Starlette's MultiPartException message text.
# These lock the mapping and the exact message strings we depend on, so a Starlette
# reword (within the >=1.3.1,<2 pin) that changes the wording fails loudly here rather
# than silently reclassifying oversize uploads. The e2e oversize/multi-file tests above
# are the complementary live-parser guard.
def test_size_exceeded_message_maps_to_413():
    exc = _too_large_or_bad_request(MultiPartException("Part exceeded maximum size of 4KB."))
    assert exc.status_code == 413


def test_too_many_files_message_maps_to_400():
    exc = _too_large_or_bad_request(MultiPartException("Too many files. Maximum number of files is 1."))
    assert exc.status_code == 400


def test_too_many_fields_message_maps_to_400():
    exc = _too_large_or_bad_request(MultiPartException("Too many fields. Maximum number of fields is 1."))
    assert exc.status_code == 400


def test_oversize_body_rejected_before_reaching_storage(client, settings, monkeypatch):
    # A body far over the limit must be refused at the transport layer, NOT after Starlette
    # spools the whole file to disk. If store_stream is reached, the body was fully buffered.
    import upsafe.routes as routes_module

    def boom(*_args, **_kwargs):
        raise AssertionError("store_stream reached — body was buffered before rejection")

    monkeypatch.setattr(routes_module, "store_stream", boom)
    huge = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_BYTES + 100_000)
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("big.png", huge, "image/png")})
    assert resp.status_code == 413
    assert _published(settings) == []


def test_rejected_upload_is_logged_without_secrets(client):
    # VF-7: 4xx rejects must be logged (observability) but redacted (no key/filename).
    buf, handler, logger = _capture_logs()
    try:
        resp = client.post(
            "/uploads",
            headers={"X-API-Key": "wrongsecretkey"},
            files={"file": ("leakyfilename.png", PNG, "image/png")},
        )
    finally:
        logger.removeHandler(handler)
    assert resp.status_code == 401
    out = buf.getvalue()
    assert "status=401" in out and "route=/uploads" in out
    assert "wrongsecretkey" not in out and "leakyfilename" not in out


def test_oversize_body_rejection_is_logged(client):
    buf, handler, logger = _capture_logs()
    huge = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_BYTES + 100_000)
    try:
        resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("big.png", huge, "image/png")})
    finally:
        logger.removeHandler(handler)
    assert resp.status_code == 413
    assert "status=413" in buf.getvalue()
