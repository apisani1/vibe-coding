"""Cross-cutting adversarial tests — the acceptance criteria that span modules."""

import io
import logging
import re

import pytest
from fastapi.testclient import TestClient

from upsafe.app import create_app
from upsafe.config import load_settings
from upsafe.logging import LOGGER_NAME
from upsafe.metadata import connect

API_KEY = "test-key"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128


@pytest.fixture()
def settings(tmp_path):
    return load_settings(env={"UPSAFE_API_KEY": API_KEY, "UPSAFE_DATA_ROOT": str(tmp_path)})


@pytest.fixture()
def client(settings):
    return TestClient(create_app(settings))


def _all_files(root):
    return {p for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "evil_name",
    [
        "../../etc/passwd.png",
        "..\\..\\windows\\system32\\evil.png",
        "/etc/cron.d/evil.png",
        "photo\tinjected.png",  # control byte in the filename, surviving transport
    ],
)
def test_traversal_filenames_are_stored_safely(client, settings, evil_name):
    before = {p for p in settings.quarantine_dir.iterdir() if p.is_file()}
    resp = client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": (evil_name, PNG, "image/png")})
    assert resp.status_code == 201

    new = [
        p
        for p in settings.quarantine_dir.iterdir()
        if p.is_file() and not p.name.startswith(".tmp-") and p not in before
    ]
    assert len(new) == 1
    # stored under a server CSPRNG name — never the attacker-controlled filename
    assert re.fullmatch(r"[0-9a-f]{32}", new[0].name)
    # the attacker's path fragments appear nowhere on disk under the data root
    assert all(
        not any(frag in p.name for frag in ("passwd", "evil", "system32", "cron", "injected"))
        for p in _all_files(settings.data_root)
    )


def test_full_cycle_leaks_no_secrets_in_logs(client):
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(handler)
    try:
        resp = client.post(
            "/uploads",
            headers={"X-API-Key": API_KEY},
            files={"file": ("sentinelfilename.png", PNG, "image/png")},
        )
        token = resp.json()["token"]
        assert client.get(f"/downloads/{token}").status_code == 200
    finally:
        logger.removeHandler(handler)

    out = buf.getvalue()
    assert out  # the requests were actually logged
    assert API_KEY not in out
    assert token not in out
    assert "sentinelfilename" not in out


def test_identical_uploads_get_distinct_names_and_tokens(client, settings):
    def upload():
        return client.post("/uploads", headers={"X-API-Key": API_KEY}, files={"file": ("same.png", PNG, "image/png")})

    t1 = upload().json()["token"]
    t2 = upload().json()["token"]
    assert t1 != t2

    conn = connect(settings.db_path)
    try:
        names = [row[0] for row in conn.execute("SELECT stored_name FROM objects").fetchall()]
    finally:
        conn.close()
    assert len(names) == 2 and len(set(names)) == 2
