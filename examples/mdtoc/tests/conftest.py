"""Shared test fixtures and helpers.

Kept dependency-light: helpers here must not import mdtoc modules that later
checkpoints introduce, so the suite collects cleanly at every checkpoint.
"""

from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"


@pytest.fixture
def golden():
    """Return a loader for a golden fixture file under ``data/``."""

    def _load(name: str) -> str:
        return (DATA_DIR / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def run_cli(tmp_path):
    """Write ``text`` to a temp ``.md``, invoke ``cli.main`` in-process, return results.

    Returns ``(exit_code, file_bytes_after, path)``. Options precede the path in
    ``args`` (e.g. ``run_cli(text, "--check")``). Capture stderr with pytest's
    ``capsys`` in the test when needed.
    """
    from mdtoc.cli import main

    def _run(text: str, *args: str, name: str = "doc.md"):
        target = tmp_path / name
        target.write_text(text, encoding="utf-8")
        code = main([*args, str(target)])
        return code, target.read_bytes(), target

    return _run
