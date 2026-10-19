#!/usr/bin/env bash
# Seed an existing v1 spec so a re-run of `define` must replace it. The case denies
# python3, so new_run_dir.py can't snapshot it — the skill must write a draft instead.
set -euo pipefail
mkdir -p vibe
cat > vibe/spec.md <<'EOF'
# Spec: mdtoc — Markdown TOC injector

Spec revision: v1 (fixture)

## Goal
Keep the table of contents of a Markdown file in sync with its headings, so authors
never hand-edit TOCs and CI can catch stale ones.

## Scope
- In (MVP): CLI `mdtoc FILE` that writes a linked TOC between `<!-- toc -->` and
  `<!-- /toc -->`; `--check`; `--max-depth N`.
- Out: multi-file mode — single file covers the stated use case.
- Out: custom anchor styles — GitHub-style slugs are the only target renderer.

## Acceptance criteria
- Running `mdtoc FILE` twice leaves the file byte-identical after the first run.
- `mdtoc --check FILE` exits 1 when the TOC is stale and 0 when current.
- `mdtoc --max-depth 2 FILE` includes only `#` and `##` headings (pytest fixture diff).

## Assumptions
- Python 3.11+, UV, pytest.
- Headings inside fenced code blocks are ignored.

## Open questions
- None.
EOF
