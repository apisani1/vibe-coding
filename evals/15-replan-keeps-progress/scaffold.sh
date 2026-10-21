#!/usr/bin/env bash
# Seed mdtoc docs mid-build: plan of 3 checkpoints, 1-2 done and ticked, 3 not started,
# and a design updated afterwards to add --dry-run. `plan` must re-plan without losing
# the finished work. Needs python3 for the run-dir/snapshot helper.
set -euo pipefail
bash "$(dirname "$0")/../13-plan-mdtoc-cli/scaffold.sh"
cat >> vibe/design.md <<'EOF'

## Dry run (design revision after the first plan)
`mdtoc --dry-run FILE` prints the file as it would be written to stdout and leaves the
file on disk unchanged. It reuses `replace_block`; the CLI only chooses between writing
and printing.
EOF
cat > vibe/plan.md <<'EOF'
# Plan: mdtoc

Upstream design: vibe/design.md (written by run 2026-10-01T11-00-00Z-design)

## Risk factors
- GitHub slug rules differ in edge cases -> mitigation: fixture-driven tests first.
- Fenced-code tracking is easy to get subtly wrong -> mitigation: dedicated tests.

## Checkpoints
### Checkpoint 1: Headings and slugs
- Does: `parse_headings` with fence tracking and `Slugger` with duplicate suffixes.
- Touches: mdtoc/headings.py, mdtoc/slug.py, tests/test_headings.py
- Verify: `uv run pytest tests/test_headings.py`

### Checkpoint 2: Render and inject
- Does: `render_toc` with `max_depth`, `replace_block`, `MarkersMissing`.
- Touches: mdtoc/render.py, mdtoc/inject.py, tests/test_inject.py
- Verify: `uv run pytest tests/test_inject.py`

### Checkpoint 3: CLI
- Does: argparse CLI with `--check` and `--max-depth`, exit codes.
- Touches: mdtoc/cli.py, tests/test_cli.py
- Verify: `uv run pytest tests/test_cli.py`

## Definition of Done
- Required: AC1-AC6 pass.
- Optional-later: README usage section.
EOF
cat > vibe/checklist.md <<'EOF'
# Checklist: mdtoc

- [x] 1. Headings and slugs — verify: `uv run pytest tests/test_headings.py`
- [x] 2. Render and inject — verify: `uv run pytest tests/test_inject.py`
- [ ] 3. CLI — verify: `uv run pytest tests/test_cli.py`
EOF
cat > vibe/verification-plan.md <<'EOF'
# Verification plan

## Checks
- `uv run pytest` proves AC1-AC6 (one test module per checkpoint).

## Cannot be verified
- none
EOF
cat > vibe/state.json <<'EOF'
{
  "target": ".",
  "greenfield_kind": "bare",
  "stage": "build",
  "last_run": "2026-10-01T12-00-00Z-plan",
  "next_mode": "verify",
  "docs": {
    "spec.md": "2026-10-01T10-00-00Z-define",
    "design.md": "2026-10-01T11-00-00Z-design",
    "plan.md": "2026-10-01T12-00-00Z-plan",
    "checklist.md": "2026-10-01T12-00-00Z-plan",
    "verification-plan.md": "2026-10-01T12-00-00Z-plan"
  },
  "open_blockers": 0,
  "gitignored": false,
  "build": {
    "approvals": ["2026-10-01T12:30:00Z checkpoint-1..2 — 'Yes, implement checkpoints 1 and 2'"],
    "completed_checkpoints": ["1", "2"],
    "last_updated": "2026-10-01T13:10:00Z"
  }
}
EOF
