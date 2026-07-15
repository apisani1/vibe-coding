# Build log

Appended by `build` after each checkpoint — never rewritten.

## 2026-07-12T23-14-01Z — Checkpoint 1: Scaffold + slug fidelity
- Approval: "Yes, implement checkpoint 1"
- Changed:
  - pyproject.toml (PEP 621; hatchling src layout; black 119 / isort profile=black /
    pytest config; dev deps pytest + markdown added via `uv add --dev`)
  - src/mdtoc/__init__.py (version + docstring)
  - src/mdtoc/slug.py (`slugify`, `unique_slug`, `IDCOUNT_RE`)
  - tests/conftest.py (`golden` loader, `DATA_DIR`)
  - tests/mdtoc/test_slug.py (fidelity table + `_<n>` trap + empty-slug + markdown
    cross-check)
  - data/section_underscore.md (fixture)
  - uv.lock, .venv (from `uv add --dev pytest markdown`)
- Verified: `uv run pytest -q tests/mdtoc/test_slug.py` → 22 passed in 0.12s. The 10
  `skipif(markdown)` cross-check cases ran (markdown installed) and confirmed our
  `slugify`/`unique_slug` match `markdown.extensions.toc` exactly.
- Notes: Corrected the test-designer's `Café→caf` expectation — NFKD drops only the
  combining accent, so `Café Menu → cafe-menu` (verified against real markdown). No
  deviations from the plan's Touches list; `[project.scripts]` entrypoint intentionally
  deferred to CP5 per plan.

## 2026-07-12T23-14-01Z — Checkpoint 2: Heading scanner
- Approval: "Aprove checkpoint 2"
- Changed:
  - src/mdtoc/headings.py (`Heading` NamedTuple, `parse_headings`, `ATX_RE`, `FENCE_RE`)
  - tests/mdtoc/test_headings.py (ATX levels, whitespace/closing-hash rules, backtick +
    tilde + info-string fences, unterminated-fence omission)
  - data/unterminated_fence.md (fixture)
- Verified: `uv run pytest -q tests/mdtoc/test_headings.py` → 11 passed in 0.03s.
- Notes: No deviations. Unterminated-fence silent omission pinned by fixture test so a
  future "fix" that raises is caught. `>6` hashes and `#NoSpace` correctly rejected.

## 2026-07-12T23-14-01Z — Checkpoint 3: Markers + TOC builder
- Approval: "Aprove checkpoint 3"
- Changed:
  - src/mdtoc/document.py (`MdtocError`/`MissingMarkersError`/`MalformedMarkersError`,
    `find_markers` [fence-aware], `build_toc`, `TOC_OPEN`/`TOC_CLOSE`/`INDENT_UNIT`);
    reuses `FENCE_RE` from headings for one shared fence model (D5)
  - tests/mdtoc/test_document.py (find_markers happy/raise paths + markers-in-fence;
    build_toc nesting, H1-skip, second-H1, relative indent, max_depth, duplicates)
  - data/duplicate_headings.md, data/markers_in_fence.md (fixtures)
- Verified: `uv run pytest -q tests/mdtoc/test_document.py -k "markers or build_toc or
  max_depth or h1 or duplicate or fence"` → 15 passed in 0.03s.
- Notes: No deviations. `render` intentionally deferred to CP4 (this module currently
  ships only the primitives). Fence-aware find_markers verified against a fixture whose
  fenced fake markers precede the real pair.

## 2026-07-12T23-14-01Z — Checkpoint 4: render orchestration (idempotence + equivalence)
- Approval: "aprove checkpoint 4"
- Changed:
  - src/mdtoc/document.py (+`render`: LF-normalize, region-excluded scan (D9),
    blank-line-fenced splice (D6b), single trailing newline (D4); +`parse_headings`
    import)
  - tests/mdtoc/test_render_idempotence.py (fixed point over 6 fixtures × depths 1/2/6,
    golden injection oracle, stale/current predicates, D2 write≡check equivalence, CRLF
    normalization)
  - data/simple.md, data/simple.expected.md (hand-written golden oracle),
    data/crlf.md (real CRLF bytes via python)
- Verified: `uv run pytest -q tests/mdtoc/test_document.py
  tests/mdtoc/test_render_idempotence.py` → 38 passed in 0.05s.
- Notes: No deviations. Hand-written `simple.expected.md` matched `render` output
  byte-for-byte (independent oracle, not self-generated), confirming the blank-line +
  trailing-newline contract. Fixed point holds across empty-TOC, populated, duplicate,
  CRLF, unterminated-fence, and markers-in-fence fixtures.

## 2026-07-12T23-14-01Z — Checkpoint 5: CLI + exit codes + packaging
- Approval: "Aprove checkpoint 5"
- Changed:
  - src/mdtoc/cli.py (`build_parser`, `main` — read/render/compare/write-or-check;
    exit 0/1/2 mapping; `OSError`→2, `MdtocError`→2, stale→1 under --check)
  - src/mdtoc/__main__.py (`python -m mdtoc`)
  - pyproject.toml (+`[project.scripts] mdtoc = "mdtoc.cli:main"`)
  - tests/conftest.py (+`run_cli` fixture)
  - tests/mdtoc/test_cli.py (all four exit-code paths, --check no-write, idempotent
    second run, max-depth via CLI, missing/malformed markers, missing file, --help)
- Verified: `uv run pytest -q tests/mdtoc/test_cli.py` → 9 passed; `uv run mdtoc --help`
  prints usage; `uv run python -m mdtoc --help` exits 0.
- Notes: No deviations. uv rebuilt/reinstalled the project to expose the console script.
  Confirmed exit 1 is reachable only via --check (plain stale run exits 0 after writing).

## 2026-07-12T23-14-01Z — Checkpoint 6: README + green suite + format gate
- Approval: "Aprove checkpoint 6"
- Changed:
  - README.md (usage, exit-code table, idempotence/`--check` invariant, Python-Markdown
    slug style, CRLF→LF + ATX-only + inline-markup limitations, marker syntax shown
    fenced so it is not self-managed)
  - pyproject.toml (`[tool.black] target-version = ["py310"]`; dev deps black + isort
    added via `uv add --dev`)
  - tests/mdtoc/test_document.py (black reformat only — collapsed multi-line string
    concatenations; no behavior change)
- Verified:
  - `uv run pytest -q` → 80 passed (exit 0)
  - `uv run black --check .` → exit 0 (12 files unchanged)
  - `uv run isort --check-only .` → exit 0
  - End-to-end dogfood on a real file: inject (exit 0) → second run produces no diff
    (idempotent) → `uv run mdtoc --check` on the current file exits 0.
- Notes: Added black + isort as **dev** deps (flagged to the user) — required to run the
  approved format gate and matching the project's Black/isort convention. Pinned Black
  `target-version = py310` to silence the Py3.15-target AST warning and match
  `requires-python`. Build complete: all 6 checkpoints green.

## Build complete — 2026-07-12T23-14-01Z
All 6 checkpoints implemented and verified. Definition of Done met: every one of the 11
acceptance criteria has a passing covering check; `uv run pytest -q` (80 tests) and the
format gate pass; both `mdtoc --help` and `python -m mdtoc --help` resolve. New deps
this run (all dev-only, user-approved): pytest, markdown, black, isort — runtime deps
remain empty. Next mode: `verify`.

## 2026-07-12T23-14-01Z — Follow-up pass: close verify findings
- Approval: "do a small build pass for both"
- Context: resolves the two findings from verify run 2026-07-13T00-06-44Z
  (findings.json): the `risk` (empty-TOC whitespace coverage gap) and the `advisory`
  (non-atomic in-place write).
- Changed:
  - src/mdtoc/cli.py (+`_atomic_write`: temp file in the target dir + `os.replace`;
    resolves symlinks via `realpath` so the real file is updated and the link
    preserved; best-effort mode preservation via `os.chmod`. Write branch now calls it
    instead of `path.write_text`.)
  - tests/mdtoc/test_render_idempotence.py (+`test_empty_toc_region_byte_form`,
    +`test_empty_toc_when_max_depth_below_all_headings` — byte-lock the empty-collapse
    branch, closing the risk)
  - tests/mdtoc/test_cli.py (+`test_write_through_symlink_updates_target_and_preserves_link`
    — pins the atomic-write symlink behavior)
- Verified: `uv run pytest -q` → 83 passed (exit 0); `uv run black --check .` → exit 0;
  `uv run isort --check-only .` → exit 0.
- Notes: No deviations. Both verify findings addressed — risk closed with a byte-level
  guard; advisory closed with atomic write (data-loss window eliminated, symlink
  semantics + file mode preserved). Runtime deps still empty (stdlib `os`/`stat`/
  `tempfile` only).

## 2026-07-13T01-10-44Z — Follow-up pass: close review advisory
- Approval: "Implement the the advisory fix and set up env/git"
- Context: resolves the sole finding from review run 2026-07-13T01-10-44Z (findings.json)
  — `_atomic_write` temp-file cleanup scoped to OSError could orphan a temp file on a
  non-OSError interrupt (Ctrl-C mid-write).
- Changed: src/mdtoc/cli.py (`_atomic_write` cleanup restructured from `except OSError`
  to a `try/finally` with a `replaced` flag — any exit before the rename unlinks the
  temp file; the original error still propagates).
- Verified: `uv run pytest -q` → 83 passed (exit 0); black --check 0; isort 0.
- Notes: No deviations. Review is now fully clean (0 open findings).
