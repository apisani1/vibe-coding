#!/usr/bin/env bash
# Seed a small existing package (functional style, argparse, JSON store) plus a spec for
# a new feature, so `design` must fit the codebase's idiom instead of inventing one.
set -euo pipefail
mkdir -p invtrack tests vibe

cat > pyproject.toml <<'EOF'
[project]
name = "invtrack"
version = "0.3.0"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
invtrack = "invtrack.cli:main"

[dependency-groups]
dev = ["pytest>=8"]
EOF

cat > invtrack/__init__.py <<'EOF'
"""Tiny inventory tracker backed by a JSON file."""
EOF

cat > invtrack/store.py <<'EOF'
"""Persistence: items live in a single JSON file as a list of dicts."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path("inventory.json")


def load_items(path: Path = DEFAULT_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_items(items: list[dict], path: Path = DEFAULT_PATH) -> None:
    path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")


def add_item(sku: str, name: str, qty: int, path: Path = DEFAULT_PATH) -> None:
    items = load_items(path)
    items.append({"sku": sku, "name": name, "qty": qty})
    save_items(items, path)
EOF

cat > invtrack/report.py <<'EOF'
"""Read-only views over the item list."""
from __future__ import annotations


def low_stock(items: list[dict], threshold: int) -> list[dict]:
    return [i for i in items if i["qty"] < threshold]


def format_table(items: list[dict]) -> str:
    rows = [f"{i['sku']:<10} {i['name']:<24} {i['qty']:>5}" for i in items]
    return "\n".join(rows)
EOF

cat > invtrack/cli.py <<'EOF'
"""argparse entry point; one subcommand per function."""
from __future__ import annotations

import argparse
import sys

from invtrack import report, store


def cmd_add(args: argparse.Namespace) -> int:
    store.add_item(args.sku, args.name, args.qty)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    items = store.load_items()
    if args.low is not None:
        items = report.low_stock(items, args.low)
    print(report.format_table(items))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="invtrack")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("sku")
    p_add.add_argument("name")
    p_add.add_argument("qty", type=int)
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list")
    p_list.add_argument("--low", type=int, default=None)
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
EOF

cat > tests/test_report.py <<'EOF'
from invtrack import report


def test_low_stock_filters_below_threshold():
    items = [{"sku": "a", "name": "A", "qty": 1}, {"sku": "b", "name": "B", "qty": 9}]
    assert report.low_stock(items, 5) == [items[0]]
EOF

cat > vibe/spec.md <<'EOF'
# Spec: CSV export for invtrack

## Goal
Let shop staff hand inventory to accounting, who only accept CSV, without retyping it.

## Scope
- In (MVP): `invtrack export --csv PATH` writes all items; `--low N` limits the export
  to items with qty < N, matching `list --low`.
- Out: Excel/XLSX — accounting accepts CSV; XLSX would add a dependency.
- Out: column selection — accounting needs every column.
- Out: import from CSV — separate feature, no demand yet.

## Constraints
- Fit the existing package: argparse CLI in `invtrack/cli.py`, plain functions over
  `list[dict]`, standard library only (`dependencies = []`).

## Acceptance criteria
- AC1: `invtrack export --csv out.csv` writes header `sku,name,qty` then one row per item
  in store order (pytest compares against a fixture file).
- AC2: `--low 5` exports only items with qty < 5 — the same rows `list --low 5` shows.
- AC3: Names containing commas or quotes round-trip through `csv.reader` unchanged.
- AC4: An empty store writes a header-only file and exits 0.
- AC5: An unwritable PATH exits 1 with `error: cannot write <PATH>` on stderr.
- AC6: Existing `add`/`list` behavior and `tests/test_report.py` still pass.

## Assumptions
- UTF-8 output, `\n` line endings.

## Open questions
- None.
EOF
