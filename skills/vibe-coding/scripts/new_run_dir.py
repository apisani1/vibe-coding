#!/usr/bin/env python3
"""
Create a new timestamped run directory under `vibe/runs/` in the target repo.

Output: prints the new directory path (absolute) to stdout.

Usage:
  new_run_dir.py --repo <path> --mode <mode> [--mode <mode> ...] [--snapshot <doc> ...] [--force]

`--repo` is required and must be an absolute path to the target repository root. The
script does not fall back to CWD because Bash CWD often resets between tool calls in
agent contexts, which silently scatters run dirs under the wrong root. Fail loudly
instead.

Layout: current docs (spec.md, design.md, plan.md, ...) live at stable paths directly
under `vibe/`; each run gets an immutable `vibe/runs/<UTC-ts>-<mode>[+<mode>...]/`. A
session that spans several modes passes `--mode` once per mode and gets one run dir.

`--snapshot <doc>` copies `vibe/<doc>` into `<run>/prior/<doc>` before the caller
overwrites it, so every replaced revision stays recoverable. Docs that don't exist yet
are skipped silently (first write).

Do NOT call this for `build` mode — build updates the current docs in place and has no
run dir. `ask` writes nothing, so it has no run dir either.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR_MODES = ("env", "define", "design", "plan", "verify", "review")
NO_RUN_DIR_MODES = {"ask", "build"}

# Markers that make a directory look like a project root. Greenfield targets may have
# none of these yet — `--force` overrides.
ROOT_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Absolute path to target root (required)")
    ap.add_argument(
        "--mode",
        required=True,
        action="append",
        help=f"One of: {', '.join(RUN_DIR_MODES)}; repeat for a multi-mode run",
    )
    ap.add_argument(
        "--snapshot",
        nargs="+",
        default=[],
        metavar="DOC",
        help="Current docs under vibe/ to copy into <run>/prior/ before they are replaced",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Skip the project-root sanity check (greenfield targets with no markers yet)",
    )
    args = ap.parse_args()

    modes: list[str] = []
    for mode in args.mode:
        if mode == "build":
            print(
                "error: do not create a run dir for `build` mode; "
                "it updates vibe/checklist.md and vibe/build-log.md in place.",
                file=sys.stderr,
            )
            return 2
        if mode == "ask":
            print("error: `ask` mode writes no artifacts and needs no run dir.", file=sys.stderr)
            return 2
        if mode not in RUN_DIR_MODES:
            print(
                f"error: unknown mode {mode!r}; expected one of "
                f"{', '.join(sorted(set(RUN_DIR_MODES) | NO_RUN_DIR_MODES))}.",
                file=sys.stderr,
            )
            return 2
        if mode not in modes:
            modes.append(mode)

    for doc in args.snapshot:
        if Path(doc).name != doc:
            print(f"error: --snapshot takes bare file names under vibe/, got {doc!r}.", file=sys.stderr)
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

    vibe = repo / "vibe"
    runs = vibe / "runs"
    runs.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = runs / f"{ts}-{'+'.join(modes)}"
    run_dir.mkdir(exist_ok=False)

    for doc in args.snapshot:
        src = vibe / doc
        if src.is_file():
            prior = run_dir / "prior"
            prior.mkdir(exist_ok=True)
            shutil.copy2(src, prior / doc)

    print(str(run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
