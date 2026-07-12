#!/usr/bin/env python3
"""
Detect which of the five vibe-coding specialist sub-agents are installed, and which
model (if any) the target repo requests for each.

Agent files are looked up in:
  - <repo>/.claude/agents/<name>.md   (project-scoped)
  - ~/.claude/agents/<name>.md        (user-scoped)
  - <skill>/../../agents/<name>.md    (skill-adjacent, when the skill ships in a
                                       repo/plugin that carries an agents/ dir)

Model requests come from <repo>/.claude/vibe-coding.local.md YAML frontmatter:

  ---
  models:
    vibe-architect: opus
    vibe-test-designer: haiku
  auto_max_checkpoints: 10
  ---

Parsing is stdlib-only and deliberately minimal (two-level "key: value" lines);
a missing or malformed file degrades to no model requests.

Emits a JSON object to stdout:
  {
    "config": {"path": "/abs/.claude/vibe-coding.local.md" | null,
               "auto_max_checkpoints": 10},
    "agents": {
      "vibe-architect": {"present": true, "path": "...", "scope": "project",
                          "model": "opus"},
      ...
    }
  }

Exit 0 always (presence info is informational; absence is not an error — the skill
falls back to inline checks, except for vibe-overseer whose absence disables --auto).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SPECIALISTS = [
    "vibe-architect",
    "vibe-test-designer",
    "vibe-code-reviewer",
    "vibe-security-auditor",
    "vibe-overseer",
]

DEFAULT_AUTO_MAX_CHECKPOINTS = 10

# skills/vibe-coding/scripts/ -> repo/plugin root two levels above the skill dir
SKILL_ADJACENT_AGENTS = Path(__file__).resolve().parent.parent.parent.parent / "agents"


def find(name: str, repo: Path) -> tuple[bool, str | None, str | None]:
    project = repo / ".claude" / "agents" / f"{name}.md"
    if project.exists():
        return True, str(project), "project"
    user = Path(os.path.expanduser("~")) / ".claude" / "agents" / f"{name}.md"
    if user.exists():
        return True, str(user), "user"
    adjacent = SKILL_ADJACENT_AGENTS / f"{name}.md"
    if adjacent.exists():
        return True, str(adjacent), "skill-adjacent"
    return False, None, None


def read_local_config(repo: Path) -> tuple[str | None, dict[str, str], int]:
    """Parse .claude/vibe-coding.local.md frontmatter. Returns (path, models, cap)."""
    cfg = repo / ".claude" / "vibe-coding.local.md"
    models: dict[str, str] = {}
    cap = DEFAULT_AUTO_MAX_CHECKPOINTS
    if not cfg.exists():
        return None, models, cap
    try:
        lines = cfg.read_text().splitlines()
    except OSError:
        return None, models, cap
    if not lines or lines[0].strip() != "---":
        return str(cfg), models, cap
    in_models = False
    for raw in lines[1:]:
        if raw.strip() == "---":
            break
        indented = raw.startswith((" ", "\t"))
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not indented:
            in_models = False
        if line == "models:":
            in_models = True
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip().strip("'\"")
        if in_models and indented:
            if key in SPECIALISTS and value:
                models[key] = value
        elif key == "auto_max_checkpoints":
            try:
                cap = max(1, int(value))
            except ValueError:
                pass
    return str(cfg), models, cap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="Target root (default: CWD)")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    cfg_path, models, cap = read_local_config(repo)

    agents: dict[str, dict] = {}
    for name in SPECIALISTS:
        present, path, scope = find(name, repo)
        agents[name] = {
            "present": present,
            "path": path,
            "scope": scope,
            "model": models.get(name),
        }

    json.dump(
        {
            "config": {"path": cfg_path, "auto_max_checkpoints": cap},
            "agents": agents,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
