# Agent Instructions

## Project Context
- Purpose: `mdtoc` — a CLI that injects/updates a linked Markdown table of contents
  between `<!-- toc -->` and `<!-- /toc -->` markers. Idempotent (re-running is a no-op),
  with a `--check` mode for CI and `--max-depth`.
- Main entrypoints: `src/mdtoc/cli.py` (`main`), the `mdtoc` console script, and
  `python -m mdtoc` (`src/mdtoc/__main__.py`). The pure core is
  `src/mdtoc/document.py::render(text, max_depth) -> str`.
- Important boundaries: the core (`render`, `build_toc`, `find_markers`, `slug`,
  `headings`) never touches the filesystem or `sys.exit`; all IO and exit-code logic
  lives in `cli.py`. Keep that separation.

## Architecture (4 modules + entrypoints)
- `slug.py` — Python-Markdown-faithful `slugify` + `unique_slug` (`_1`/`_2` collisions).
  Do not swap for a looser `endswith` suffix check; the anchored `IDCOUNT_RE` is
  load-bearing.
- `headings.py` — `parse_headings` (ATX only, fence-aware; unterminated fence silently
  omits later headings, by design).
- `document.py` — `render`, `find_markers` (fence-aware), `build_toc`, and the
  `MdtocError` hierarchy.
- `cli.py` — argparse + `_atomic_write` (temp file + `os.replace`, symlink/mode
  preserving).

## Invariants — do not break (tests enforce these)
- **Idempotence / fixed point:** `render(render(t)) == render(t)`; "current" means
  `render(t) == t`, the single predicate shared by the writer and `--check`.
- **Whitespace contract:** body fenced by exactly one blank line each side; empty TOC
  collapses to one blank line; `render` output ends with exactly one trailing newline and
  uses LF. The CLI applies this only when it actually writes — a file whose TOC is already
  current is left byte-for-byte untouched (its line endings are preserved).
- **Exit codes:** `0` ok/current, `1` stale (only under `--check`), `2` usage/IO/marker
  error. `1` must never leak into the write path.
- **Zero runtime dependencies** — stdlib only. `markdown` is a *dev* dep (slug
  cross-check test) and must not become a runtime import.

## How To Work Here
- Read existing patterns before changing code; prefer small, reviewable changes.
- Define/extend a test before or alongside any behavior change (the suite is the spec).
- Slug behavior is pinned against the real Python-Markdown package by a cross-check test;
  keep it passing.
- Report commands run and checks skipped.

## Common Commands
- Install: `uv sync`
- Test: `uv run pytest -q`
- Format: `uv run black . && uv run isort .`
- Lint: `uv run flake8 src tests` (config `[tool.flake8]`, read via the
  `flake8-pyproject` plugin — stock flake8 can't read `pyproject.toml`) and
  `uv run pylint src/mdtoc` (config `[tool.pylint.*]`; src only, tests excluded). Both
  max line 119.
- Typecheck: `uv run mypy src/mdtoc` (config `[tool.mypy]`, `strict = true`).
- Gate (CI): `uv run black --check . && uv run isort --check-only . && uv run flake8 src tests && uv run pylint src/mdtoc && uv run mypy src/mdtoc`
- Run: `uv run mdtoc <file.md>` · `uv run mdtoc --check <file.md>` · `python -m mdtoc <file.md>`

## Guardrails
- Always: run `uv run pytest -q` and the gate (black + isort + flake8) before declaring
  work done.
- Ask first: adding any dependency (`uv add` mutates `pyproject.toml` + lockfile);
  changing the slug algorithm, the whitespace contract, or exit codes (public contracts).
- Never: add a runtime dependency; break the idempotence fixed point; make the core touch
  the filesystem or call `sys.exit`.

## Approval Boundary
Do not edit files, install packages, run migrations, commit, deploy, delete data,
or perform other mutating work without explicit written approval.
