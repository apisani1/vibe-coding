import pytest
from fastapi import HTTPException

from upsafe.auth import require_api_key
from upsafe.config import load_settings


@pytest.fixture()
def settings():
    return load_settings(env={"UPSAFE_API_KEY": "s3cret-key", "UPSAFE_DATA_ROOT": "."})


def test_correct_key_accepted(settings):
    dep = require_api_key(settings)
    assert dep(x_api_key="s3cret-key") is None


def test_wrong_key_rejected(settings):
    dep = require_api_key(settings)
    with pytest.raises(HTTPException) as exc:
        dep(x_api_key="wrong")
    assert exc.value.status_code == 401


def test_missing_key_rejected(settings):
    dep = require_api_key(settings)
    with pytest.raises(HTTPException) as exc:
        dep(x_api_key=None)
    assert exc.value.status_code == 401


def test_empty_key_rejected(settings):
    dep = require_api_key(settings)
    with pytest.raises(HTTPException):
        dep(x_api_key="")


def test_prefix_of_key_rejected(settings):
    dep = require_api_key(settings)
    with pytest.raises(HTTPException):
        dep(x_api_key="s3cret")  # length-mismatch must not pass
