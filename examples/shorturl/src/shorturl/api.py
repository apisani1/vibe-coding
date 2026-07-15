"""The Flask HTTP application.

`create_app` wires a per-request SQLite connection, the API-key gate over ``/api/*``, and
the routes: the public redirect (``GET /<code>``) plus the authenticated create endpoint
(``POST /api/codes``). Stats are added in a later checkpoint on the same factory.

Each request gets its own connection (opened in ``before_request``, closed in teardown):
SQLite connections are not safe to share across the server's worker threads, so a fresh
one per request is the simple, correct choice.
"""

from __future__ import annotations

import hmac
import sqlite3
from typing import Any

from flask import (
    Flask,
    Response,
    g,
    jsonify,
    redirect,
    request,
)

from . import (
    codes,
    db,
)
from .config import Config

# How many times to regenerate an auto code on the (astronomically rare) PK collision.
_AUTO_CODE_ATTEMPTS = 5


def create_app(config: Config) -> Flask:
    """Build the Flask app for the given configuration."""
    app = Flask(__name__)
    app.config["shorturl_config"] = config

    # Ensure the schema exists once, up front, rather than on every request.
    bootstrap = db.connect(config.db_path)
    try:
        db.init_schema(bootstrap)
    finally:
        bootstrap.close()

    @app.before_request
    def _open_connection() -> None:
        g.conn = db.connect(config.db_path)

    @app.before_request
    def _require_api_key() -> Any:
        """Guard ``/api/*`` with the configured key; the redirect route stays public."""
        if not request.path.startswith("/api/"):
            return None
        provided = request.headers.get("X-API-Key")
        if not provided:
            return _error(401, "unauthorized", "missing API key")
        expected = config.api_key or ""
        # Compare on bytes: hmac.compare_digest raises TypeError on non-ASCII str, and
        # header values arrive latin-1-decoded, so a high-byte key must fail closed (403),
        # not crash (500).
        if not expected or not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
            return _error(403, "forbidden", "invalid API key")
        return None

    @app.teardown_appcontext
    def _close_connection(_exc: BaseException | None) -> None:
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    @app.post("/api/codes")
    def create_code() -> Any:
        """Create a short code (auto or custom alias), optionally with an expiry."""
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or "url" not in body:
            return _error(400, "bad_request", "body must be JSON with a 'url' field")
        try:
            target_url = codes.validate_url(str(body["url"]))
            alias = _optional_alias(body)
            expires_at = _optional_expiry(body)
        except ValueError as exc:
            return _error(400, "bad_request", str(exc))

        created_at = codes.to_iso(codes.utcnow())
        try:
            code = _persist_code(g.conn, alias, target_url, created_at, expires_at)
        except _AliasTaken:
            return _error(409, "conflict", "that alias is already taken")
        except _CodeSpaceExhausted:
            return _error(500, "internal_error", "could not allocate a unique code")

        payload = {
            "code": code,
            "short_url": f"{config.base_url}/{code}",
            "target_url": target_url,
            "expires_at": expires_at,
        }
        return jsonify(payload), 201

    @app.get("/api/codes/<code>/stats")
    def code_stats(code: str) -> Any:
        """Return per-code analytics: total, per-day series, and top referers."""
        row = db.get_code(g.conn, code)
        if row is None:
            return _error(404, "not_found", "no such code")
        stats = db.get_stats(g.conn, code)
        payload = {
            "code": code,
            "target_url": row["target_url"],
            "status": codes.status(row["active"], row["expires_at"], codes.utcnow()),
            "total": stats["total"],
            "series": stats["series"],
            "top_referers": stats["top_referers"],
        }
        return jsonify(payload)

    @app.get("/<code>")
    def redirect_code(code: str) -> Any:
        """Public redirect: 302 to the target (recording a click), else 404/410."""
        row = db.get_code(g.conn, code)
        if row is None:
            return _error(404, "not_found", "no such code")
        now = codes.utcnow()
        if not codes.is_serving(row["active"], row["expires_at"], now):
            return _error(410, "gone", "this code has expired")
        try:
            db.insert_click(
                g.conn,
                code=code,
                clicked_at=codes.to_iso(now),
                referer=request.headers.get("Referer"),
                user_agent=request.headers.get("User-Agent"),
            )
        except sqlite3.IntegrityError:
            # The code was deleted (FK cascade) between the lookup and the click insert;
            # treat it as gone rather than surfacing a 500.
            return _error(404, "not_found", "no such code")
        return redirect(row["target_url"], code=302)

    return app


class _AliasTaken(Exception):
    """The requested custom alias already exists."""


class _CodeSpaceExhausted(Exception):
    """Auto-generation failed to find a free code within the retry budget."""


def _optional_alias(body: dict[str, Any]) -> str | None:
    raw = body.get("alias")
    if raw is None:
        return None
    return codes.validate_alias(str(raw))


def _optional_expiry(body: dict[str, Any]) -> str | None:
    raw = body.get("expires_at")
    if raw is None:
        return None
    return codes.normalize_expires_at(str(raw))


def _persist_code(
    conn: sqlite3.Connection,
    alias: str | None,
    target_url: str,
    created_at: str,
    expires_at: str | None,
) -> str:
    """Insert the code, generating a unique one when no alias is given.

    Uniqueness is enforced by the ``codes`` primary key; a custom alias that collides is
    a client conflict (``_AliasTaken``), while an auto-code collision is retried.
    """
    if alias is not None:
        try:
            db.insert_code(conn, code=alias, target_url=target_url, created_at=created_at, expires_at=expires_at)
        except sqlite3.IntegrityError as exc:
            raise _AliasTaken(alias) from exc
        return alias

    for _ in range(_AUTO_CODE_ATTEMPTS):
        code = codes.generate_code()
        try:
            db.insert_code(conn, code=code, target_url=target_url, created_at=created_at, expires_at=expires_at)
        except sqlite3.IntegrityError:
            continue
        return code
    raise _CodeSpaceExhausted()


def _error(status: int, error: str, message: str) -> tuple[Response, int]:
    """Return a JSON error body with the given HTTP status."""
    return jsonify({"error": error, "message": message}), status
