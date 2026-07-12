---
description: Vibe-coding lifecycle — ask | env | define | design | plan | build | verify | review
argument-hint: <mode> [target] [--ci] [--json] [--auto]
---

Activate the **vibe-coding** skill with these arguments: $ARGUMENTS

Parse positional args as `<mode> [target] [--ci] [--json] [--auto]`:

- `mode` — one of `ask`, `env`, `define`, `design`, `plan`, `build`, `verify`,
  `review`. If missing or ambiguous, ask which mode the user wants (suggest the next
  pipeline mode based on `.claude/vibe-reports/latest` when it exists).
- `target` — path to the target project root; defaults to the current working
  directory.
- `--ci` — headless mode (valid for `verify` and `review` only).
- `--json` — stream `findings.json` to stdout.
- `--auto` — autopilot (valid for `build` only): vibe-overseer assumes the approver
  role per the skill's Approval boundaries; refuse if vibe-overseer is not installed.

Follow the skill's SKILL.md workflow exactly: read `references/modes.md` for the
requested mode before acting, respect the run-directory semantics, and enforce the
approval boundaries (`build` and `env` mutate only after explicit written approval).
