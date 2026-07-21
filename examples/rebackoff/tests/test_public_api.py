"""The public API surface: exports are importable and __all__ is exactly the surface."""

import importlib.resources

import rebackoff

EXPECTED = {
    "retry",
    "aretry",
    "Retrying",
    "AsyncRetrying",
    "RetryPolicy",
    "RetryError",
    "Attempt",
    "JITTER_NAMES",
    "__version__",
}


def test_all_exports_are_importable():
    for name in EXPECTED:
        assert hasattr(rebackoff, name), name


def test_all_matches_expected_surface():
    assert set(rebackoff.__all__) == EXPECTED


def test_version_is_a_string():
    assert isinstance(rebackoff.__version__, str)
    assert rebackoff.__version__


def test_jitter_names_are_the_documented_set():
    assert set(rebackoff.JITTER_NAMES) == {"full", "equal", "none", "decorrelated"}


def test_py_typed_marker_is_shipped():
    assert importlib.resources.files("rebackoff").joinpath("py.typed").is_file()
