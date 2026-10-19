#!/usr/bin/env bash
# Seed an approved spec so `design` has its upstream doc.
set -euo pipefail
mkdir -p vibe
cat > vibe/spec.md <<'EOF'
# Spec: mdtoc — Markdown TOC injector

## Goal
Keep the table of contents of a Markdown file in sync with its headings, so authors
never hand-edit TOCs and CI can catch stale ones.

## Scope
- In (MVP): CLI `mdtoc FILE` that writes a linked TOC between `<!-- toc -->` and
  `<!-- /toc -->`; `--check`; `--max-depth N`.
- Out: multi-file mode — single file covers the stated use case.
- Out: custom anchor styles — GitHub-style slugs are the only target renderer.
- Out: HTML block parsing — headings inside raw HTML are rare in target docs.

## Constraints
- Python 3.11+, standard library only at runtime; UV; pytest.

## Acceptance criteria
- AC1: Running `mdtoc FILE` twice leaves the file byte-identical after the first run.
- AC2: `mdtoc --check FILE` exits 1 when the TOC is stale and 0 when current, without
  modifying the file.
- AC3: `mdtoc --max-depth 2 FILE` includes only `#` and `##` headings (fixture diff).
- AC4: Duplicate heading texts get GitHub-style `-1`, `-2` anchor suffixes (fixture diff).
- AC5: Headings inside fenced code blocks are not listed (fixture diff).
- AC6: A file with no markers exits 2 with `error: no <!-- toc --> markers` on stderr
  and is left unchanged.

## Assumptions
- Files are UTF-8; line endings are preserved as found.

## Open questions
- None.
EOF
