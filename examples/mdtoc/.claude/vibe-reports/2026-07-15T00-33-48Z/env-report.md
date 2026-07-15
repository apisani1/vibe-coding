# Agent environment report

Re-audit of an already-provisioned environment (first `env` run: `2026-07-13T01-17-36Z`).
The workshop is in good shape; this run finds two small maintenance items, not a rebuild.

## Current state

- **Agent instructions exist and are accurate.** `CLAUDE.md` (read by Claude Code) and
  `AGENTS.md` (read by Codex/other agents) both sit at the repo root. They are template-
  conformant and short enough to read every session: project purpose + entrypoints, the
  4-module architecture, the non-breakable invariants (idempotence fixed point, whitespace
  contract, exit codes, zero runtime deps), the UV command set, and always/ask-first/never
  guardrails + approval boundary.
- **Rest of the workshop is complete.** `README.md` accurate; `pyproject.toml` fully
  configured (black/isort line-length 119, flake8 via flake8-pyproject, pylint src-only,
  mypy `strict`, hatchling build); `.github/workflows/ci.yml` present (test matrix
  py3.10–3.13 + a `quality` gate running black/isort/flake8/pylint/mypy); git repo on
  `main`. No `agent-knowledge/` needed — the deep context lives in the spec/design/
  decisions artifacts, and the tool is small.
- **`make`/pre-commit intentionally absent.** This repo predates the generate-project
  structure, so the global "run `make pre-commit`" preference does not apply; the direct
  `uv run …` commands documented in `CLAUDE.md` are the correct workflow here.

## Findings

1. **Duplicated agent doc, two independent files.** `CLAUDE.md` and `AGENTS.md` are
   byte-identical (3694 bytes) but are two separate regular files — not a symlink. They
   are currently kept in sync by hand (edit timestamps 11:21 vs 11:56 on the same day).
   With a single source they cannot drift; as two hand-maintained copies they eventually
   will. *(This is a workflow decision — see Proposed changes B; nothing is applied until
   you choose.)*

2. **Guardrails shorthand under-lists the gate.** The `## Guardrails` → "Always" line
   describes the pre-done gate as `(black + isort + flake8)`, but the authoritative
   `## Common Commands` → "Gate (CI)" line and `.github/workflows/ci.yml`'s `quality` job
   now also run **pylint** and **mypy** (added in commits `7645a4d`, `eded4eb`). The
   shorthand drifted behind the real gate.

## Proposed changes

### A. Fix the Guardrails shorthand (edit `CLAUDE.md`, mirror to `AGENTS.md`)

```diff
 ## Guardrails
-- Always: run `uv run pytest -q` and the gate (black + isort + flake8) before declaring
-  work done.
+- Always: run `uv run pytest -q` and the full gate (black + isort + flake8 + pylint +
+  mypy) before declaring work done.
```

### B. Resolve the duplication (your choice — I will not apply until you pick)

- **Option B1 (recommended): make `AGENTS.md` a symlink to `CLAUDE.md`.** Single source of
  truth; edits can never diverge. Codex still reads `AGENTS.md`, Claude Code still reads
  `CLAUDE.md`. Trade-off: a native-Windows checkout may materialize the symlink as a text
  file rather than a link (fine for this personal repo; worth noting).
- **Option B2: keep two files, add a one-line "keep in sync with AGENTS.md/CLAUDE.md" note
  at the top of each.** Portable everywhere; sync stays manual.
- **Option B3: leave as-is.** Accept the manual-sync burden.

If you pick B1 or B2, change A is written into `CLAUDE.md` and then propagated to
`AGENTS.md` per the chosen mechanism (symlink → automatic; two-file → mirrored edit).

## Applied

- Nothing yet. `env` writes to the repo **only after explicit written approval**. Awaiting
  your go-ahead on change A and your choice of B1 / B2 / B3.
