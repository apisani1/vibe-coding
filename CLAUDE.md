# CLAUDE.md — vibe-coding

Repo-specific guidance for Claude Code working in this repository. This **overrides**
global defaults where they conflict (notably: no `make pre-commit` here).

## What this repo is

The **source repo for the `vibe-coding` Claude Code plugin** — a skill that manages the
full lifecycle of building software with AI agents (spec → design → plan → build →
verify → review, plus `ask` and `env`). It ships the skill, a `/vibe` command, and five
read-only specialist sub-agents. See `README.md` for install/usage and `SKILL.md` for
the orchestrator design.

## No code / no build toolchain — pre-commit is NOT needed

This is a **documentation-and-config repo**: Markdown instructions and JSON manifests,
plus two small **standard-library-only** Python helper scripts
(`skills/vibe-coding/scripts/{new_run_dir,probe_subagents}.py`). There is **no
application code, no build system, no package, no dependencies, and no lint/format/test
toolchain**.

Therefore, when creating a commit here:
- **Do not run `make pre-commit` / `make check`** — there is no Makefile and no
  formatting or linting step. Skip it; it is not needed.
- The global "run `make pre-commit` before commits" preference does **not** apply to
  this repo.
- Still keep commits atomic and use the emoji conventional-commit format
  (e.g. `✨ feat: …`, `📝 docs: …`, `🔧 chore: …`).
- **Only commit or push when explicitly asked.** `main` is the working branch.

## Repository layout

```
.claude-plugin/        # plugin.json + marketplace.json (plugin packaging)
skills/vibe-coding/     # the skill: SKILL.md, references/, scripts/, evals/
agents/                # 5 vibe-* sub-agents (read-only tools, fenced-JSON contract)
commands/vibe.md       # /vibe <mode> [target] [--ci] [--json] [--auto]
README.md              # install + usage + acknowledgments
vibe-coding.png        # workflow diagram used in the README
skills/vibe-coding-workspace/   # eval/dev workspace — gitignored, not shipped
```

## Testing changes (no deps required)

- **Python scripts:** run with **`python3`** (bare `python` may be 2.7 on macOS and will
  fail). They take `--repo <path>`; no install step.
- **Probe dispatch naming** (`probe_subagents.py`): emits a per-agent `invoke_name` —
  bare for user/project installs, `vibe-coding:<agent>` under a plugin (detected via
  `.claude-plugin/plugin.json` beside the skill-adjacent `agents/` dir). When changing
  it, re-check: project scope → bare; skill-adjacent + manifest → namespaced;
  malformed/absent manifest → bare; absent agent → `invoke_name: null`.
- **JSON manifests:** `python3 -m json.tool .claude-plugin/plugin.json` (and
  `marketplace.json`) to validate.
- **Agents:** validate with plugin-dev's
  `skills/agent-development/scripts/validate-agent.sh <agent>.md`.
- **Consistency:** the skill dispatches sub-agents by the probe's `invoke_name` — never a
  hardcoded name. Keep `SKILL.md`, `references/schemas.md`, and `references/modes.md`
  aligned on that rule and on the findings.json category allow-list.

## Editing conventions

- Reference docs use progressive disclosure: keep `SKILL.md` lean and push detail into
  `references/*.md`. Match the existing terse, imperative style.
- Runtime artifacts the skill produces always live under the **target** repo's
  `.claude/vibe-reports/<UTC-timestamp>/`, never in this repo or the user's home.

## Sources

Built on / inspired by Islem Maboud's Agentic Engineering Skills, Forrest Chang's LLM
behavioral skill (Karpathy's Claude Code guidelines), and Arjan Egges's 7-step Software
Design Guide. Full credits in `README.md`.

See @./notes for additional development ideas