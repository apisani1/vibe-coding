#!/usr/bin/env python3
"""
Read the user's vibe-coding preference profile.

The profile is user-scoped (one place, not per repo) and is consulted **only for bare
greenfield** builds, where the repo has no conventions of its own to detect. Default
location:

  ~/.claude/vibe-coding/profile/
  ├── preferences.md      # YAML frontmatter (tool choices) + prose body (style philosophy)
  └── assets/             # literal files copied VERBATIM into a new repo
      ├── .editorconfig
      ├── .gitignore
      ├── .vscode/settings.json
      └── .pre-commit-config.yaml

`preferences.md` frontmatter is parsed with a deliberately minimal stdlib parser (same
approach as probe_subagents.py's read_local_config): scalar `key: value`, inline lists
`key: [a, b]`, and block lists (`key:` then indented `- item` lines). Anything fancier is
out of scope — keep profiles simple.

Emits a JSON object to stdout:
  {
    "profile_dir": "/abs/path",
    "present": true,
    "preferences": {"package_manager": "uv", "line_length": "119",
                     "linter": ["flake8", "pylint"], ...},
    "prose": "…style philosophy body…",
    "assets": [".editorconfig", ".gitignore", ".vscode/settings.json", ...]
  }

Exit 0 always. A missing profile is not an error — the caller falls back to generic
defaults (`present: false`, empty preferences/assets).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_PROFILE_DIR = Path(os.path.expanduser("~")) / ".claude" / "vibe-coding" / "profile"


def _parse_value(raw: str) -> str | list[str]:
    """Scalar, or an inline list `[a, b, c]`. Quotes stripped."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        items = [i.strip().strip("'\"") for i in raw[1:-1].split(",")]
        return [i for i in items if i]
    return raw.strip("'\"")


def _frontmatter_open(lines: list[str]) -> int | None:
    """Index just after the opening `---`, tolerating leading blank lines and a leading
    HTML comment block (profiles are hand-edited). Returns None if no frontmatter."""
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if s.startswith("<!--"):
            while i < n and "-->" not in lines[i]:
                i += 1
            i += 1  # consume the line with -->
            continue
        break
    if i < n and lines[i].strip() == "---":
        return i + 1
    return None


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split `---`-fenced YAML-ish frontmatter from the prose body.

    Returns (preferences, prose). No frontmatter -> ({}, whole text).
    """
    lines = text.splitlines()
    start = _frontmatter_open(lines)
    if start is None:
        return {}, text.strip()

    prefs: dict[str, object] = {}
    body_start = len(lines)
    pending_key: str | None = None  # active block-list key
    for idx in range(start, len(lines)):
        raw = lines[idx]
        if raw.strip() == "---":
            body_start = idx + 1
            break
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        indented = raw.startswith((" ", "\t"))

        # Continuation of a block list: `  - item`
        if pending_key and indented and line.startswith("- "):
            item = line[2:].strip().strip("'\"")
            if item:
                prefs.setdefault(pending_key, [])
                if isinstance(prefs[pending_key], list):
                    prefs[pending_key].append(item)  # type: ignore[union-attr]
            continue

        if not indented:
            pending_key = None
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not value:
            # `key:` with nothing after → opens a block list
            pending_key = key
            continue
        prefs[key] = _parse_value(value)

    prose = "\n".join(lines[body_start:]).strip()
    return prefs, prose


def list_assets(assets_dir: Path) -> list[str]:
    """Asset paths relative to assets/, so they map onto the target repo root."""
    if not assets_dir.is_dir():
        return []
    out: list[str] = []
    for p in sorted(assets_dir.rglob("*")):
        if p.is_file():
            out.append(str(p.relative_to(assets_dir)))
    return out


def read_profile(profile_dir: Path) -> dict[str, object]:
    prefs_file = profile_dir / "preferences.md"
    preferences: dict[str, object] = {}
    prose = ""
    present = False
    if prefs_file.exists():
        present = True
        try:
            preferences, prose = parse_frontmatter(prefs_file.read_text())
        except OSError:
            present = False
    assets = list_assets(profile_dir / "assets")
    # A bare assets/ dir with no preferences.md still counts as a usable profile.
    if assets:
        present = True
    return {
        "profile_dir": str(profile_dir),
        "present": present,
        "preferences": preferences,
        "prose": prose,
        "assets": assets,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Profile directory (default: ~/.claude/vibe-coding/profile)",
    )
    args = ap.parse_args()
    result = read_profile(Path(os.path.expanduser(args.profile_dir)).resolve())
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
