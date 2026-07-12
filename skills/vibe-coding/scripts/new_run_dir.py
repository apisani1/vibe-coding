#!/usr/bin/env python3
"""
Create a new timestamped vibe-report run directory and update the `latest` pointer.

Output: prints the new directory path (absolute) to stdout.

Usage:
  new_run_dir.py --repo <path> --mode <mode> [--force]

`--repo` is required and must be an absolute path to the target repository root. The
script does not fall back to CWD because Bash CWD often resets between tool calls in
agent contexts, which silently scatters run dirs under the wrong root. Fail loudly
instead.

The `latest` pointer is a plain text file (not a symlink), for Windows compatibility.
Pointer write is atomic: tempfile + rename.

Do NOT call this for `build` mode — build operates in place on the directory that
`latest` currently points to. `ask` writes nothing, so it has no run dir either.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR_MODES = {"env", "define", "design", "plan", "verify", "review"}
NO_RUN_DIR_MODES = {"ask", "build"}

# Markers that make a directory look like a project root. Greenfield targets may have
# none of these yet — `--force` overrides.
ROOT_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Absolute path to target root (required)")
    ap.add_argument("--mode", required=True, help=f"One of: {', '.join(sorted(RUN_DIR_MODES))}")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Skip the project-root sanity check (greenfield targets with no markers yet)",
    )
    args = ap.parse_args()

    if args.mode == "build":
        print(
            "error: do not create a new run dir for `build` mode; "
            "operate in place on `latest`.",
            file=sys.stderr,
        )
        return 2
    if args.mode == "ask":
        print("error: `ask` mode writes no artifacts and needs no run dir.", file=sys.stderr)
        return 2
    if args.mode not in RUN_DIR_MODES:
        print(
            f"error: unknown mode {args.mode!r}; expected one of "
            f"{', '.join(sorted(RUN_DIR_MODES | NO_RUN_DIR_MODES))}.",
            file=sys.stderr,
        )
        return 2

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: --repo {repo} is not a directory.", file=sys.stderr)
        return 2
    if not args.force and not any((repo / m).exists() for m in ROOT_MARKERS):
        print(
            f"error: --repo {repo} does not look like a project root "
            f"(none of {', '.join(ROOT_MARKERS)} found). Pass the project root, "
            "or use --force for a greenfield directory.",
            file=sys.stderr,
        )
        return 2

    reports = repo / ".claude" / "vibe-reports"
    reports.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = reports / ts
    run_dir.mkdir(exist_ok=False)

    pointer = reports / "latest"
    fd, tmp_path = tempfile.mkstemp(dir=str(reports), prefix=".latest.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(ts + "\n")
        os.replace(tmp_path, pointer)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise

    print(str(run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
