# Plan: mdtoc — Markdown TOC injector

Upstream design: ../2026-07-12T22-43-14Z/design.md
Upstream spec: ../2026-07-12T22-36-21Z/spec.md
Verification: ./verification-plan.md (every checkpoint's `Verify:` is defined there)

## Risk factors (ArjanCodes step 5 — identified first)
- **R1 — Slug/collision fidelity diverges from Python-Markdown.** Links silently break in
  MkDocs/Sphinx. → Front-load as Checkpoint 1; table-driven fidelity tests incl. the
  `_<n>` anchored-regex trap and empty-slug case; optional dev-only cross-check against
  the real `markdown` package.
- **R2 — `render` is not actually a fixed point** (whitespace/newline/blank-line drift
  breaks idempotence and the `--check`≡write invariant). → Checkpoint 4 owns it with an
  explicit fixed-point test *and* a check/write-equivalence test over diverse fixtures;
  golden `.md` files make the whitespace contract (D6b/D4) reviewable.
- **R3 — Fence model desync** shared by `parse_headings` and `find_markers` (unterminated
  fence, markers-in-fence). → One fence model, region-excluded scan (D9); fixtures run
  against both consumers (Checkpoints 2–3).
- **R4 — Packaging/entrypoint** (`uv` console_scripts) doesn't resolve. → Checkpoint 5
  verifies `uv run mdtoc --help` and `python -m mdtoc --help`; a missing entrypoint is a
  blocker, not a flake.

## Checkpoints
Small, independently verifiable slices; risk front-loaded (R1 first, R2 at CP4). Flat
list — this is one small single-subsystem tool, so phases add no value.

### Checkpoint 1: Scaffold + slug fidelity (R1)
- Does: create the UV project — `pyproject.toml` (PEP 621; `[tool.black] line-length=119`,
  `[tool.isort] profile=black`, `[tool.pytest.ini_options]`; `markdown` as a **dev-only**
  dep), `src/mdtoc/__init__.py`, `tests/` tree, `data/` fixtures dir. Implement `slug.py`:
  `slugify` (NFKD, ASCII-drop, `[^\w\s-]` strip, lower, `[-\s]+`→`-`) and `unique_slug`
  (`IDCOUNT_RE = r'(.*)_([0-9]+)$'`, `_1`/bump, empty→`_1`).
- Touches: `pyproject.toml`, `src/mdtoc/__init__.py`, `src/mdtoc/slug.py`,
  `tests/conftest.py`, `tests/mdtoc/test_slug.py`, `data/section_underscore.md`.
- Verify: `uv run pytest -q tests/mdtoc/test_slug.py` (table incl. `_<n>` trap,
  empty-slug, Unicode drop, collisions) — proves AC1/AC7 slug half.

### Checkpoint 2: Heading scanner (R3)
- Does: `headings.py` — `Heading(level, text)` and `parse_headings(lines)`: single pass,
  fenced-code toggle (```` ``` ````/`~~~`), ATX regex `^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$`
  (whitespace-after-hashes required; closing `#`s stripped). Unterminated fence → silent
  omission to EOF.
- Touches: `src/mdtoc/headings.py`, `tests/mdtoc/test_headings.py`,
  `data/unterminated_fence.md`.
- Verify: `uv run pytest -q tests/mdtoc/test_headings.py` (ATX rules, `#NoSpace` not a
  heading, empty-text heading, fence skip, unterminated fence) — AC10.

### Checkpoint 3: Markers + TOC builder (R3)
- Does: in `document.py` — the `MdtocError` hierarchy (`MissingMarkersError`,
  `MalformedMarkersError`); `find_markers(lines)` (fence-aware, first well-formed pair,
  else raise); `build_toc(headings, max_depth)` (drop leading H1, `level<=max_depth`
  filter, relative 2-space indentation, slug assignment via CP1 with one shared `used`
  set, `- [text](#slug)` lines).
- Touches: `src/mdtoc/document.py`, `tests/mdtoc/test_document.py`,
  `data/duplicate_headings.md`, `data/markers_in_fence.md`.
- Verify: `uv run pytest -q tests/mdtoc/test_document.py -k "markers or build_toc or
  max_depth or h1 or duplicate or fence"` — AC5, AC6, AC7 (doc half), AC8 (raise), AC10
  (markers-in-fence).

### Checkpoint 4: render orchestration — idempotence + equivalence (R2)
- Does: `render(text, max_depth)` in `document.py` — LF-normalize; `find_markers`;
  scan only `lines[:open_i] + lines[close_i+1:]` (D9); splice body with the pinned
  blank-line contract (D6b); single trailing newline (D4). Golden input/expected
  fixtures.
- Touches: `src/mdtoc/document.py`, `tests/mdtoc/test_document.py`,
  `tests/mdtoc/test_render_idempotence.py`, `data/simple.md`, `data/simple.expected.md`,
  `data/crlf.md`.
- Verify: `uv run pytest -q tests/mdtoc/test_document.py tests/mdtoc/test_render_idempotence.py`
  — `test_injection_golden` (AC1), `test_fixed_point` + `test_check_write_equivalence`
  (AC2/AC3/AC4 core), byte-exact blank-line/newline contract.

### Checkpoint 5: CLI + exit codes + packaging (R4)
- Does: `cli.py` — argparse (`path`, `--check`, `--max-depth` int default 6); read file
  (catch `OSError`→exit 2), call `render`, compare; write-if-different else exit 0;
  `--check` exits 1 on mismatch / 0 if current, never writes; map `MdtocError`→exit 2 with
  stderr. `__main__.py`; `[project.scripts] mdtoc = "mdtoc.cli:main"` in `pyproject.toml`.
- Touches: `src/mdtoc/cli.py`, `src/mdtoc/__main__.py`, `pyproject.toml`,
  `tests/mdtoc/test_cli.py`.
- Verify: `uv run pytest -q tests/mdtoc/test_cli.py && uv run mdtoc --help && uv run
  python -m mdtoc --help` — AC3, AC4, AC8, AC9, AC11; all four exit-code paths, `1`
  reachable only via `--check`.

### Checkpoint 6: README + green suite + format gate
- Does: `README.md` (usage, exit codes 0/1/2, the idempotence/`--check` invariant, slug
  style, CRLF→LF caveat, marker syntax — with the marker example fenced so mdtoc doesn't
  self-manage it). Ensure the whole suite + formatters pass.
- Touches: `README.md`, minor test/format touch-ups only.
- Verify: `uv run pytest -q && uv run black --check . && uv run isort --check-only .`
  — AC11 (suite green) + convention gate.

## Definition of Done
- Required: Checkpoints 1–6 green; all 11 acceptance criteria have a passing covering
  check; `uv run pytest -q` and the format gate pass; `uv run mdtoc --help` and
  `python -m mdtoc --help` resolve.
- Optional-later: the `markdown`-package cross-check test (dev-only, `skipif` when
  absent) may land in CP1 or be deferred without blocking DoD; all spec "Out of scope"
  items (multi-file, `--slug-style`, Setext, auto-insert, `--min-depth`) stay deferred.

## Migration / one-off scripts
None.
