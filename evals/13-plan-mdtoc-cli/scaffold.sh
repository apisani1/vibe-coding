#!/usr/bin/env bash
# Seed an approved spec + design for mdtoc so `plan` has its upstream docs.
set -euo pipefail
bash "$(dirname "$0")/../09-design-mdtoc-cli/scaffold.sh"
cat > vibe/design.md <<'EOF'
# Design: mdtoc

Upstream spec: vibe/spec.md (written by run 2026-10-01T10-00-00Z-define)

## Overview
A stdlib-only package `mdtoc` with a pure core and a thin CLI. The core reads the file
text, finds headings (skipping fenced code blocks), builds GitHub-style anchors, renders
a nested bullet list, and replaces the text between the `<!-- toc -->` and
`<!-- /toc -->` markers. `--check` renders the TOC and compares it to the current block
without writing.

## Module & component design
- `mdtoc/headings.py`: `parse_headings(text) -> list[Heading]` — tracks fence state
  (``` and ~~~, length-aware) so headings inside code blocks are skipped (AC5).
- `mdtoc/slug.py`: `Slugger` — GitHub-style slug (lowercase, strip punctuation, spaces to
  `-`), with a per-document counter producing `-1`, `-2` suffixes for duplicates (AC4).
- `mdtoc/render.py`: `render_toc(headings, max_depth) -> str` (AC3).
- `mdtoc/inject.py`: `replace_block(text, toc) -> str`; raises `MarkersMissing` (AC6),
  preserves the file's line endings.
- `mdtoc/cli.py`: argparse; `mdtoc FILE [--check] [--max-depth N]`; exit codes 0 / 1
  (stale, `--check`) / 2 (usage or missing markers).

## Key algorithms & libraries
- Slug rules follow GitHub's renderer; only the standard library is used.
- Idempotence (AC1) follows from rendering deterministically and replacing the whole
  block.

## Edge cases & failure modes
- No markers: `MarkersMissing` -> stderr message, exit 2, file untouched (AC6).
- Duplicate headings: counter keyed on the base slug (AC4).
- Empty file or no headings: empty TOC block, still idempotent.
- CRLF files: detect the dominant line ending and reuse it.

## Ripple effects
- README gets a usage section.
EOF
