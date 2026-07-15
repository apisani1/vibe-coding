import http.client
import threading

import pytest
from waitress import create_server

from shorturl import (
    codes,
    db,
)
from shorturl.api import create_app
from shorturl.cli import main
from shorturl.config import (
    Config,
    ConfigError,
)


def test_help_lists_all_subcommands(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for command in ("serve", "list", "expire", "delete"):
        assert command in out


def test_serve_fails_closed_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SHORTURL_DB", str(tmp_path / "s.db"))
    monkeypatch.delenv("SHORTURL_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        main(["serve"])


def test_base_url_from_env_is_echoed_in_create(tmp_path, monkeypatch):
    # Reverse-proxy story: SHORTURL_BASE_URL drives the returned short_url.
    monkeypatch.setenv("SHORTURL_DB", str(tmp_path / "s.db"))
    monkeypatch.setenv("SHORTURL_API_KEY", "k")
    monkeypatch.setenv("SHORTURL_BASE_URL", "https://proxy.example")
    client = create_app(Config.from_env()).test_client()
    resp = client.post("/api/codes", json={"url": "https://a.com", "alias": "px"}, headers={"X-API-Key": "k"})
    assert resp.status_code == 201
    assert resp.get_json()["short_url"] == "https://proxy.example/px"


def test_serve_boots_and_redirects_over_a_real_socket(tmp_path):
    # AC #14: the app actually boots under waitress on a real (ephemeral) port and serves.
    db_path = str(tmp_path / "s.db")
    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        db.insert_code(
            conn,
            code="smoke",
            target_url="https://example.com/ok",
            created_at=codes.to_iso(codes.utcnow()),
            expires_at=None,
        )
    finally:
        conn.close()

    config = Config(db_path=db_path, api_key="k", host="127.0.0.1", port=0, base_url="http://x")
    server = create_server(create_app(config), host="127.0.0.1", port=0)
    shutting_down = threading.Event()

    def run_server() -> None:
        try:
            server.run()
        except OSError:
            # Closing the listening socket from the main thread races the asyncore loop
            # and raises a benign "bad file descriptor" during teardown; only real,
            # pre-shutdown errors should propagate.
            if not shutting_down.is_set():
                raise

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    try:
        client = http.client.HTTPConnection("127.0.0.1", server.effective_port, timeout=5)
        client.request("GET", "/smoke")
        resp = client.getresponse()
        assert resp.status == 302
        assert resp.getheader("Location") == "https://example.com/ok"
        client.close()
    finally:
        shutting_down.set()
        server.close()
        thread.join(timeout=5)
