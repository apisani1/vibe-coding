import hashlib
import io
import logging

import pytest
from fastapi.testclient import TestClient

from upsafe.app import create_app
from upsafe.config import load_settings
from upsafe.logging import LOGGER_NAME
from upsafe.metadata import connect

API_KEY = "test-key"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
PAST = "2000-01-01T00:00:00+00:00"


@pytest.fixture()
def settings(tmp_path):
    return load_settings(env={"UPSAFE_API_KEY": API_KEY, "UPSAFE_DATA_ROOT": str(tmp_path)})


@pytest.fixture()
def client(settings):
    return TestClient(create_app(settings))


def _upload(client, name="photo.png", content=PNG):
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": (name, content, "image/png")})
    assert resp.status_code == 201
    return resp.json()["token"]


def _expire(settings, token):
    conn = connect(settings.db_path)
    try:
        conn.execute("UPDATE objects SET expires_at = ? WHERE token = ?", (PAST, token))
    finally:
        conn.close()


def test_round_trip_returns_exact_bytes_with_safe_headers(client):
    token = _upload(client)
    resp = client.get(f"/downloads/{token}")  # note: no API key — token is the capability
    assert resp.status_code == 200
    assert resp.content == PNG
    assert hashlib.sha256(resp.content).hexdigest() == hashlib.sha256(PNG).hexdigest()
    assert resp.headers["content-type"].startswith("image/png")
    assert resp.headers["content-disposition"].startswith("attachment")
    assert "photo.png" in resp.headers["content-disposition"]
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_unknown_token_returns_404(client):
    resp = client.get("/downloads/deadbeefdeadbeefdeadbeef")
    assert resp.status_code == 404


def test_expired_token_returns_404(client, settings):
    token = _upload(client)
    _expire(settings, token)
    assert client.get(f"/downloads/{token}").status_code == 404


def _norm_headers(resp):
    # per-request/volatile headers can't be part of the opacity contract
    return {k.lower(): v for k, v in resp.headers.items() if k.lower() != "date"}


def test_unknown_and_expired_are_indistinguishable(client, settings):
    token = _upload(client)
    _expire(settings, token)
    expired = client.get(f"/downloads/{token}")
    missing = client.get("/downloads/deadbeefdeadbeefdeadbeef")
    assert expired.status_code == missing.status_code == 404
    assert expired.content == missing.content  # byte-identical bodies
    assert _norm_headers(expired) == _norm_headers(missing)  # and identical header sets (VF-1)


def test_healthz_needs_no_auth_and_leaks_nothing(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_download_404_logs_route_template_not_token(client):
    # VF-7 + criterion 10: the reject is logged, but as the route TEMPLATE, never the token.
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    token = "SECRETTOKENABCDEF0123456789"
    try:
        resp = client.get(f"/downloads/{token}")
    finally:
        logger.removeHandler(handler)
    assert resp.status_code == 404
    out = buf.getvalue()
    assert "route=/downloads/{token}" in out
    assert "status=404" in out
    assert token not in out


def test_docs_and_openapi_disabled_by_default(client):
    # VF-4: no unauthenticated schema/UI surface unless explicitly enabled
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_docs_served_when_explicitly_enabled(tmp_path):
    settings = load_settings(
        env={"UPSAFE_API_KEY": API_KEY, "UPSAFE_DATA_ROOT": str(tmp_path), "UPSAFE_ENABLE_DOCS": "true"}
    )
    dev_client = TestClient(create_app(settings))
    assert dev_client.get("/openapi.json").status_code == 200
    assert dev_client.get("/docs").status_code == 200
