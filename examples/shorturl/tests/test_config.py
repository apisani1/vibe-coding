import pytest

from shorturl.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    Config,
    ConfigError,
)


def test_from_env_uses_defaults_when_empty():
    cfg = Config.from_env({})
    assert cfg.db_path == "shorturl.db"
    assert cfg.api_key is None
    assert cfg.host == DEFAULT_HOST
    assert cfg.port == DEFAULT_PORT
    assert cfg.base_url == f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"


def test_from_env_reads_all_values():
    cfg = Config.from_env(
        {
            "SHORTURL_DB": "/data/s.db",
            "SHORTURL_API_KEY": "secret",
            "SHORTURL_HOST": "0.0.0.0",
            "SHORTURL_PORT": "9090",
        }
    )
    assert cfg.db_path == "/data/s.db"
    assert cfg.api_key == "secret"
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9090
    # base_url derived from host/port when not given explicitly
    assert cfg.base_url == "http://0.0.0.0:9090"


def test_base_url_override_wins_and_is_stripped():
    cfg = Config.from_env({"SHORTURL_BASE_URL": "https://sho.rt/"})
    assert cfg.base_url == "https://sho.rt"


def test_require_api_key_raises_when_missing():
    cfg = Config.from_env({})
    with pytest.raises(ConfigError):
        cfg.require_api_key()


def test_require_api_key_returns_key_when_present():
    cfg = Config.from_env({"SHORTURL_API_KEY": "k"})
    assert cfg.require_api_key() == "k"


def test_blank_api_key_is_treated_as_missing():
    cfg = Config.from_env({"SHORTURL_API_KEY": ""})
    assert cfg.api_key is None


def test_bad_port_raises():
    with pytest.raises(ConfigError):
        Config.from_env({"SHORTURL_PORT": "not-a-number"})


def test_out_of_range_port_raises():
    with pytest.raises(ConfigError):
        Config.from_env({"SHORTURL_PORT": "70000"})
