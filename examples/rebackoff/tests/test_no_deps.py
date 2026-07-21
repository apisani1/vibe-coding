"""AC14: rebackoff imports zero third-party runtime modules and declares zero deps."""

import pathlib
import subprocess
import sys
import tomllib

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_no_third_party_runtime_imports():
    # Import the package in a clean, isolated interpreter and confirm that nothing loaded
    # from site-packages (other than rebackoff itself, installed from ./src).
    # Measure only the modules that importing rebackoff ADDS (a snapshot diff), so venv
    # bootstrap modules already present at interpreter startup are not miscounted.
    code = (
        "import sys\n"
        "before = set(sys.modules)\n"
        "import rebackoff\n"
        "added = set(sys.modules) - before\n"
        "bad = []\n"
        "for name in added:\n"
        "    if name.startswith('rebackoff'):\n"
        "        continue\n"
        "    f = getattr(sys.modules[name], '__file__', None) or ''\n"
        "    if 'site-packages' in f or 'dist-packages' in f:\n"
        "        bad.append(name)\n"
        "print(','.join(sorted(bad)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", f"unexpected third-party imports: {result.stdout!r}"


def test_pyproject_declares_zero_runtime_dependencies():
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    assert data["project"].get("dependencies", []) == []
