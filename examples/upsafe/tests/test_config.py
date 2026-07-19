import pytest

from upsafe.config import (
    DEFAULT_ALLOWED_TYPES,
    DEFAULT_MAX_UPLOAD_BYTES,
    DEFAULT_TOKEN_TTL_SECONDS,
    ConfigError,
    load_settings,
)


def test_missing_api_key_fails_fast():
    with pytest.raises(ConfigError):
        load_settings(env={})


def test_blank_api_key_fails_fast():
    with pytest.raises(ConfigError):
        load_settings(env={"UPSAFE_API_KEY": "   "})


def test_defaults_applied(tmp_path):
    settings = load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_DATA_ROOT": str(tmp_path)})
    assert settings.api_key == "k"
    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES
    assert settings.token_ttl_seconds == DEFAULT_TOKEN_TTL_SECONDS
    assert dict(settings.allowed_types) == DEFAULT_ALLOWED_TYPES
    assert settings.enable_docs is False  # secure default: no docs/openapi


@pytest.mark.parametrize("raw,expected", [("true", True), ("1", True), ("on", True), ("false", False), ("0", False)])
def test_enable_docs_flag_parsed(raw, expected):
    settings = load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_ENABLE_DOCS": raw})
    assert settings.enable_docs is expected


def test_invalid_enable_docs_rejected():
    with pytest.raises(ConfigError):
        load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_ENABLE_DOCS": "maybe"})


def test_derived_paths(tmp_path):
    settings = load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_DATA_ROOT": str(tmp_path)})
    assert settings.quarantine_dir == settings.data_root / "quarantine"
    assert settings.db_path == settings.data_root / "upsafe.db"


def test_api_key_is_stripped():
    settings = load_settings(env={"UPSAFE_API_KEY": "  secret  ", "UPSAFE_DATA_ROOT": "."})
    assert settings.api_key == "secret"


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1.5"])
def test_invalid_max_upload_bytes_rejected(bad):
    with pytest.raises(ConfigError):
        load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_MAX_UPLOAD_BYTES": bad})


def test_custom_limits_parsed():
    settings = load_settings(
        env={
            "UPSAFE_API_KEY": "k",
            "UPSAFE_MAX_UPLOAD_BYTES": "2048",
            "UPSAFE_TOKEN_TTL_SECONDS": "60",
        }
    )
    assert settings.max_upload_bytes == 2048
    assert settings.token_ttl_seconds == 60


def test_allowed_extensions_subset_normalized():
    settings = load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_ALLOWED_EXTENSIONS": ".PNG, txt"})
    assert set(settings.allowed_types) == {"png", "txt"}


def test_unknown_extension_rejected():
    with pytest.raises(ConfigError):
        load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_ALLOWED_EXTENSIONS": "exe"})


def test_empty_allow_list_rejected():
    with pytest.raises(ConfigError):
        load_settings(env={"UPSAFE_API_KEY": "k", "UPSAFE_ALLOWED_EXTENSIONS": " , "})
