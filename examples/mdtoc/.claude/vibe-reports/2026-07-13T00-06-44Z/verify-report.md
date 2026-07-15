# Verify report

Plan under test: ../2026-07-12T23-14-01Z/verification-plan.md
Build under test: ../2026-07-12T23-14-01Z (all 6 checkpoints)

## Passed
- `uv run pytest -q` — **80 passed, 0 failed, 0 skipped** (exit 0). The `markdown`
  cross-check tests ran (markdown 3.10.2 present), so slug fidelity is verified against
  the authoritative Python-Markdown algorithm, not just a hand table.
- `uv run black --check .` — exit 0 (12 files unchanged).
- `uv run isort --check-only .` — exit 0 (only `.venv` skipped).
- `uv run mdtoc --help` — exit 0, prints usage (AC11).
- `uv run python -m mdtoc --help` — exit 0 (AC11, module entrypoint).
- End-to-end dogfood on a real file: inject (exit 0) → second run byte-identical
  (idempotent, `diff` empty) → `--check` on the current file exits 0.

### Acceptance criteria — all 11 verified by a genuine passing check
Confirmed by vibe-test-designer reading every source/test/fixture (not nominal):
- AC1 injection + slug fidelity — `test_injection_golden` (byte-locked) + real
  Python-Markdown cross-check.
- AC2 idempotence — `test_fixed_point` (6 fixtures × 3 depths), `test_second_run_no_change`,
  `test_current_write_check_equivalence` (D2 elevated to its own test).
- AC3/AC4 `--check` current/stale — exit 0 / exit 1, file unmodified in both.
- AC5 `--max-depth` — unit (depth 2 & 4) + CLI.
- AC6 leading-H1 skip — positive, negative, only-first, starts-at-H2.
- AC7 duplicate anchors — `_1` suffix + the `IDCOUNT_RE` bump-not-`endswith` trap.
- AC8 missing/malformed markers — exit 2, unmodified, stderr names markers.
- AC9 missing file — exit 2, non-empty stderr.
- AC10 code fences — backtick/tilde/info-string/marker-in-fence + unterminated-fence
  silent omission.
- AC11 packaging — both entrypoints + green suite executed.
- Exit-code contract (D6): 0/1/2 all exercised; `1` reachable only via `--check`.
  CRLF→LF + single trailing newline asserted.

## Failed
- None.

## Not run (cannot be verified locally — declared in the plan, not a regression)
- **True MkDocs/Sphinx anchor resolution** — we assert the slug *string* matches the
  Python-Markdown algorithm (and cross-check against the real package); rendering the
  doc and clicking the anchor is out of scope.
- **CRLF round-tripping in a real Windows editor** — we test CRLF→LF normalization and
  stability; editor behavior is by-design out of scope (D4).
- **Wheel/install into a clean venv** — `uv run mdtoc --help` proves the local
  entrypoint resolves, not `pip install mdtoc` in a fresh environment.

## Coverage gaps
- **[risk] Empty-TOC managed-region whitespace is not byte-asserted** (vibe-test-designer).
  The populated form is byte-locked by `simple.expected.md`, but the empty branch
  (`render` splicing an empty body — only-leading-H1 docs, or `--max-depth` below all
  headings) is only covered by `test_fixed_point`, which a wrong blank-line count would
  still satisfy. Plan check (g)'s empty-collapse clause. One-line golden assertion or a
  small `empty_toc.expected.md` fixture closes it. See `findings.json`.

## Security
- **[advisory] Non-atomic in-place write + symlink follow** (vibe-security-auditor).
  Truncate-then-write risks corrupting the user's file on an interrupted run; both are
  defense-in-depth, not exploitable in a local single-user CLI. No blockers: input is
  validated, no injection sink, no ReDoS (regexes timed linear), runtime deps empty, dev
  deps pinned. "Safe to ship from a security standpoint." Highest-value hardening:
  temp-file + `os.replace()`.

## Verdict
**PASS.** All 11 acceptance criteria are verified by passing checks; the full suite,
format gate, and both entrypoints are green. No blockers and no failing checks. Two
non-blocking follow-ups recorded: one `risk` (a verification gap on the empty-TOC
whitespace — a missing test, not a code defect) and one `advisory` (atomic-write
hardening). CI semantics: exit 0 (no blockers).
