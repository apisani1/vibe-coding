# Verification plan

Written by `plan` before any code exists; executed by `verify`. Drafted by
vibe-test-designer against spec.md (11 acceptance criteria) and design.md.

## How to run everything

```bash
uv run pytest -q                              # full suite (pure core + CLI/exit-code)
uv run pytest -q tests/mdtoc/test_slug.py     # focused, when only slugging changes
uv run mdtoc --help                           # AC11 packaging smoke
uv run python -m mdtoc --help
uv run black --check . && uv run isort --check-only .   # format gate
```

Verification is dominated by `uv run pytest` on the pure `render(text, max_depth) -> str`
core (string-in/string-out, no temp files), with a thin band of CLI tests via `tmp_path`
+ in-process `cli.main` for exit codes and file side-effects. This split mirrors D1: the
interesting logic is provable without the filesystem; only the exit-code/IO wiring needs
the CLI harness.

## pytest layout

```
tests/
  conftest.py                     # shared fixtures (below)
  mdtoc/
    test_slug.py                  # slugify + unique_slug fidelity      (AC1, AC7)
    test_headings.py              # parse_headings: ATX rules, fences   (AC10)
    test_document.py              # render: markers, splice, H1, depth  (AC1,2,5,6,8)
    test_render_idempotence.py    # fixed-point + check/write equiv     (AC2,3,4)
    test_cli.py                   # argv -> exit code + file effects    (AC3,4,8,9,11)
  data/                           # golden .md fixtures (input + expected)
    simple.md / simple.expected.md, crlf.md, unterminated_fence.md,
    markers_in_fence.md, duplicate_headings.md, section_underscore.md
```

Central fixtures (`conftest.py`): a `render` alias; `run_cli(tmp_path, *args, text=...)`
that writes `text` to a `.md`, calls `cli.main([...])` in-process, and returns
`(exit_code, file_bytes_after, stderr)`; a parametrized `slug_cases` table; a
`golden(name)` loader. Prefer golden `.md` files for full-document `render` assertions so
the exact whitespace/newline contract (D6b/D4) is reviewable, not buried in escaped
string literals.

## Criteria — acceptance-criterion → check coverage matrix

| AC | Criterion | Check(s) |
| --- | --- | --- |
| 1 | Injection: nested `[text](#slug)` list, faithful slug | `test_document::test_injection_golden`; `test_slug` table |
| 2 | Idempotence: 2nd run identical | `test_render_idempotence::test_fixed_point`; `test_cli::test_second_run_no_change` |
| 3 | `--check` current → exit 0, file untouched | `test_cli::test_check_current` (bytes+mtime unchanged, code 0) |
| 4 | `--check` stale → non-zero, file untouched | `test_cli::test_check_stale` (code 1, bytes unchanged) |
| 5 | `--max-depth` filters by absolute level | `test_document::test_max_depth[2]` and `[4]` |
| 6 | Leading H1 skipped; H2+ appear | `test_document::test_leading_h1_skipped` + `test_second_h1_listed` |
| 7 | Duplicate text → distinct anchors, 2nd `_1`, both present | `test_slug::test_unique_slug`; `test_document::test_duplicate_headings` |
| 8 | Missing markers → unmodified, non-zero, stderr names markers | `test_cli::test_missing_markers` (code 2); `test_document::test_missing_markers_raises` |
| 9 | Missing/unreadable file → non-zero, stderr, no write | `test_cli::test_missing_file` (code 2) |
| 10 | `#` inside code fence not a heading | `test_headings::test_fence_skipped`; `test_document::test_markers_and_headings_in_fence` |
| 11 | `uv run mdtoc --help` runs; suite passes | `uv run mdtoc --help`; `uv run python -m mdtoc --help`; green suite |

## Checks — hardest requirements (where it actually breaks)

- **(a) Idempotence fixed point + check/write equivalence (D2).**
  `test_fixed_point`: for every fixture `t` and depth `d`, `render(render(t,d),d) ==
  render(t,d)`, over a *diverse* fixture set (empty TOC, populated, empty body, CRLF,
  deep tree). `test_check_write_equivalence`: `(render(t,d)==t) == (main([path]) writes
  nothing) == (main(['--check',path]) returns 0)` — makes D2 a first-class test, not an
  emergent property of AC2/3/4.
- **(b) Slug + `_1`/`_2` fidelity incl. text ending `_<n>`.** Table-driven `slugify`
  (Unicode drop `Café→caf`, punctuation strip, whitespace collapse, empty-text `## `→
  empty slug). `unique_slug` anchored-regex trap: `Section _2` → bare `section-_2` first,
  a genuine collision on it bumps to `section-_3` (per `IDCOUNT_RE`), **not**
  `section-_2_1`; assert an `endswith` shortcut would fail this. Empty slug → `_1`.
- **(c) Fence skipping incl. two edges (D5/D9).** Marker+heading inside a fence → neither
  scanned as heading nor treated as marker. **Unterminated fence** (odd fence count) →
  later headings silently dropped, no error (pinned so a future "fix" that raises is
  caught). Both ```` ``` ```` and `~~~` toggle.
- **(d) Leading-H1 skip.** Negative case (doc starting at H2 drops nothing);
  `--max-depth 1` + leading H1 yields an empty TOC without error.
- **(e) `--max-depth`.** H1–H4 fixture: `--max-depth 2` yields only levels ≤2 (after H1
  skip); `--max-depth 4` includes H4. Relative indentation (D7): shallowest kept level at
  column 0, 2-space unit.
- **(f) Exit codes 0/1/2 (D6).** One CLI test per code; `1` reachable *only* via
  `--check`; assert a plain stale run (no `--check`) exits 0 after writing — `1` must not
  leak into the write path.
- **(g) Blank-line contract (D6b) + trailing newline (D4).** Golden-byte assertion:
  `<!-- toc -->\n\n- [..](#..)\n...\n\n<!-- /toc -->`, empty-TOC collapsing to one blank
  line between markers, exactly one trailing newline at EOF.

## External signals
None. No network, telemetry, persisted state, deployed endpoint, or logs. The only side
effect is bytes written to the single target file (none under `--check`) — captured by
`run_cli`.

## Risk-based expansion
- `slug.py` changed → full `slugify`/`unique_slug` table **and** the optional
  Python-Markdown cross-check (slugs are the public link contract).
- splice/whitespace/newline (`render`, D6b/D4) → re-run the entire idempotence fixture
  matrix, not one case.
- fence model (`parse_headings` or `find_markers`) → exercise fence fixtures against
  **both** consumers, incl. unterminated + marker-in-fence.
- `cli.py` → all four exit-code paths (CI branches on 1 vs 2).

## Cannot be verified locally
- **True MkDocs/Sphinx anchor resolution** — we assert the slug *string* matches the
  Python-Markdown algorithm; the local proxy is the optional dev-only cross-check against
  the real `markdown` package (a **test/dev** dep, never runtime per D3). Rendering the
  doc and clicking the anchor is out of scope.
- **CRLF round-tripping in a real Windows editor** — we test CRLF→LF normalization + then
  stable; editor behavior is by-design out of scope (D4).
- **Wheel/install correctness beyond `uv run`** — `uv run mdtoc --help` proves the local
  entrypoint resolves, not `pip install mdtoc` in a fresh venv. Acceptable for MVP.

## Adopted from test-designer findings
- Add the **optional** `markdown`-cross-check test, `@pytest.mark.skipif(markdown absent)`
  — runtime stays zero-dependency (D3); it is a dev dependency only.
- AC11: run both `uv run mdtoc --help` and `uv run python -m mdtoc --help`; a missing
  entrypoint is a **blocker** against AC11, not a flake.
- Elevate the D2 equivalence to its own explicit test (see check (a)).
