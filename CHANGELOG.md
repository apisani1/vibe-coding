## [2.0.0] - 2026-10-20

### Breaking Changes
- Run artifacts moved from `.claude/vibe-reports/<timestamp>/` (plus a `latest` pointer)
  to a visible, git-tracked `vibe/` folder in the target repo. Headless sessions cannot
  write under `.claude/`, so the old layout broke CI and non-interactive runs. There is
  no legacy fallback: re-create any project that used the old layout.
  - Current docs (`spec.md`, `design.md`, `decisions.md`, `plan.md`, `checklist.md`,
    `verification-plan.md`, `build-log.md`) live at stable paths directly under `vibe/`.
  - Each run keeps an immutable `vibe/runs/<UTC-ts>-<mode>[+<mode>]/` record
    (`summary.md`, `state.json`, mode reports, and `prior/` snapshots of replaced docs).
  - `vibe/STATUS.md` (human view) and `vibe/state.json` (machine view) replace the
    `latest` pointer and hold the build state.
  - Reports from `verify`, `review` and `env` stay only in the run folder.
  - The skill never edits `.gitignore`; if `vibe/` is ignored it says so in `STATUS.md`.
- Run-level `state.json` gains `docs_written`; `upstream_artifacts` now lists `vibe/`
  paths.

### Added
- `vibe/STATUS.md` and the project-level `vibe/state.json` schema.
- `new_run_dir.py --snapshot DOC...` copies docs about to be replaced into the run's
  `prior/` folder, and `--mode` is repeatable so a multi-mode session shares one run folder.
- Re-planning rule: finished checkpoints are carried forward ticked and the `build` object
  in `vibe/state.json` is preserved.
- Plugin eval suite (`evals/`, 16 cases) for `define`, `design` and `plan`, run with
  `claude plugin eval` against a no-plugin baseline. Cases that seed files need `--scaffold`.
- `fin` worked example (AI trading workstation) and a Claude PR Assistant workflow.

### Changed
- `define` quality gate: every acceptance criterion must be checkable by a test, command,
  exit code, log line or file comparison with a concrete threshold ("by review" alone no
  longer counts), and every Out-of-scope item needs its own one-line reason.
- Helper scripts must be run as their own Bash call, never chained. A denied command does
  not mean Bash is unavailable, so each script is still tried on its own.
- Preference-profile gating clarified: tool choices apply to bare greenfield only; assets
  may be seeded into any repo on explicit request, add-only.
- Profile-asset collisions are resolved (union files append-merge, structured files
  key-merge, existing values win) instead of being discarded.
- Run artifacts now reflect what actually happened.
- `plugin.json` version bumped to 2.0.0.

### Fixed
- If `new_run_dir.py` cannot run, no timestamp or run folder is invented, and an existing
  `vibe/` doc is never overwritten: the new version is written as `vibe/<doc>.draft.md`
  and the summary names it.

### Documentation
- README, `SKILL.md`, `modes.md`, `schemas.md`, `templates.md`, `ci-recipe.md` and
  `worked-example.md` updated for the `vibe/` layout; duplicated rules cut across docs and
  agents.
