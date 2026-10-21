#!/usr/bin/env bash
# Seed the invtrack package + CSV-export spec (same as case 11) and an approved design.
set -euo pipefail
bash "$(dirname "$0")/../11-design-existing-codebase/scaffold.sh"
cat > vibe/design.md <<'EOF'
# Design: CSV export for invtrack

Upstream spec: vibe/spec.md (written by run 2026-10-01T10-00-00Z-define)

## Overview
Add an `export` subcommand to the existing argparse CLI. Formatting lives in a pure
function in `invtrack/report.py` next to `low_stock`; the command function in
`invtrack/cli.py` loads items, optionally filters with `report.low_stock`, and writes the
file. Standard library `csv` only.

## Module & component design
- `invtrack/report.py`: add `format_csv(items: list[dict]) -> str` using `csv.writer`
  with `lineterminator="\n"`; header `sku,name,qty`.
- `invtrack/cli.py`: add `cmd_export(args)` and an `export` subparser with `--csv PATH`
  (required) and `--low N`. On `OSError` while writing: print
  `error: cannot write <PATH>` to stderr and return 1.
- Tests in `tests/test_export.py` (pytest, same style as `tests/test_report.py`) with a
  fixture CSV under `tests/data/`.

## Edge cases & failure modes
- Empty store: header-only file, exit 0.
- Names with commas/quotes: handled by `csv.writer` quoting.
- Unwritable path: exit 1 with the stderr message.

## Ripple effects
- README usage section gets an `export` example.
EOF
