"""Runtime configuration, read once from the environment into an immutable object.

Construction is kept separate from use: callers build a ``Config`` (usually via
``Config.from_env``) and pass it in, rather than reading ``os.environ`` deep inside the
API or CLI. This keeps those layers testable with an explicit config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Environment variable names, in one place so the CLI/API/docs agree.
ENV_DB = "SHORTURL_DB"
ENV_API_KEY = "SHORTURL_API_KEY"
ENV_HOST = "SHORTURL_HOST"
ENV_PORT = "SHORTURL_PORT"
ENV_BASE_URL = "SHORTURL_BASE_URL"

DEFAULT_DB = "shorturl.db"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a usable configuration."""


@dataclass(frozen=True)
class Config:
    """Immutable service configuration.

    ``api_key`` is optional because the admin CLI operates directly on the database and
    needs no key; only ``serve`` requires one (enforced by :meth:`require_api_key`), so
    the API is never exposed without authentication.
    """

    db_path: str
    api_key: str | None
    host: str
    port: int
    base_url: str

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Config:
        """Build a ``Config`` from ``environ`` (defaults to ``os.environ``).

        ``base_url`` defaults to ``http://{host}:{port}`` and can be overridden (e.g.
        behind a reverse proxy or on a custom domain) via ``SHORTURL_BASE_URL``.
        """
        env = os.environ if environ is None else environ
        host = env.get(ENV_HOST, DEFAULT_HOST)
        port = _parse_port(env.get(ENV_PORT))
        base_url = env.get(ENV_BASE_URL) or f"http://{host}:{port}"
        return cls(
            db_path=env.get(ENV_DB, DEFAULT_DB),
            api_key=env.get(ENV_API_KEY) or None,
            host=host,
            port=port,
            base_url=base_url.rstrip("/"),
        )

    def require_api_key(self) -> str:
        """Return the API key, or raise ``ConfigError`` if none is configured.

        Called by ``serve`` so the service fails closed rather than exposing an
        unauthenticated create endpoint.
        """
        if not self.api_key:
            raise ConfigError(
                f"{ENV_API_KEY} must be set to run the server "
                "(the create/stats API must not be exposed without a key)."
            )
        return self.api_key


def _parse_port(raw: str | None) -> int:
    if raw is None or raw == "":
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{ENV_PORT} must be an integer, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"{ENV_PORT} must be in 1..65535, got {port}")
    return port
