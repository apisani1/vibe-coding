"""Immutable, env-derived configuration.

Why a frozen dataclass built by a function rather than reading ``os.environ`` at the
point of use: a single typed, test-injectable ``Settings`` lets ``create_app(settings)``
separate construction from use, and lets tests build apps against a ``tmp_path`` data
root and a known API key. ``load_settings`` fails fast so the service refuses to start
misconfigured (e.g. with no API key) rather than accepting uploads it cannot protect.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Mapping,
    Optional,
)

DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB
DEFAULT_TOKEN_TTL_SECONDS = 24 * 60 * 60  # 24 hours
# Extension -> served MIME type. The value is what downloads report; the client's
# declared content type is never trusted. The signature table in ``validation.py``
# pins each of these to its magic bytes (text types use the text-safety check).
DEFAULT_ALLOWED_TYPES: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a valid, safe configuration."""


@dataclass(frozen=True)
class Settings:
    """Fully-resolved runtime configuration. Immutable by construction."""

    api_key: str
    data_root: Path
    max_upload_bytes: int
    token_ttl_seconds: int
    allowed_types: Mapping[str, str]
    enable_docs: bool

    @property
    def quarantine_dir(self) -> Path:
        return self.data_root / "quarantine"

    @property
    def db_path(self) -> Path:
        return self.data_root / "upsafe.db"


def _positive_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{key} must be a positive integer, got {value}")
    return value


_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return default if value == "" else False
    raise ConfigError(f"{key} must be a boolean (true/false), got {raw!r}")


def _resolve_allowed_types(env: Mapping[str, str]) -> dict[str, str]:
    raw = env.get("UPSAFE_ALLOWED_EXTENSIONS")
    if raw is None or raw.strip() == "":
        return dict(DEFAULT_ALLOWED_TYPES)
    selected: dict[str, str] = {}
    for token in raw.split(","):
        ext = token.strip().lower().lstrip(".")
        if not ext:
            continue
        if ext not in DEFAULT_ALLOWED_TYPES:
            raise ConfigError(
                f"UPSAFE_ALLOWED_EXTENSIONS lists {ext!r}, which has no known content "
                f"signature; supported: {', '.join(sorted(DEFAULT_ALLOWED_TYPES))}"
            )
        selected[ext] = DEFAULT_ALLOWED_TYPES[ext]
    if not selected:
        raise ConfigError("UPSAFE_ALLOWED_EXTENSIONS resolved to an empty allow-list")
    return selected


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    """Build ``Settings`` from the environment, failing fast on unsafe/invalid values."""
    env = os.environ if env is None else env

    api_key = env.get("UPSAFE_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("UPSAFE_API_KEY must be set to a non-empty value")

    data_root = Path(env.get("UPSAFE_DATA_ROOT", "./upsafe-data")).expanduser().resolve()

    return Settings(
        api_key=api_key,
        data_root=data_root,
        max_upload_bytes=_positive_int(env, "UPSAFE_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
        token_ttl_seconds=_positive_int(env, "UPSAFE_TOKEN_TTL_SECONDS", DEFAULT_TOKEN_TTL_SECONDS),
        allowed_types=_resolve_allowed_types(env),
        # Interactive docs / OpenAPI schema are OFF by default — opt in for local dev only.
        enable_docs=_bool(env, "UPSAFE_ENABLE_DOCS", False),
    )
