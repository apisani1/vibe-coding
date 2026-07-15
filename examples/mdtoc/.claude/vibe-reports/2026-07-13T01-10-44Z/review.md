# Review

Scope reviewed: full greenfield build — `src/mdtoc/{slug,headings,document,cli,__main__,__init__}.py`,
`tests/mdtoc/*.py`, `tests/conftest.py`, `pyproject.toml`, `README.md` (incl. the
post-verify `_atomic_write` follow-up).
Upstream artifacts (ground truth): spec.md (2026-07-12T22-36-21Z), design.md +
decisions.md (2026-07-12T22-43-14Z), plan.md (2026-07-12T23-14-01Z).
Sub-agents: vibe-code-reviewer, vibe-security-auditor.

## Correctness
No issues. vibe-code-reviewer traced each named risk area against the code and probed
edge cases directly:
- **`render` splice / idempotence** (`document.py:81-97`): fixed point holds; empty branch
  collapses to one blank line, populated branch fences the body with one blank line each
  side (D6b), `rstrip("\n") + "\n"` guarantees the single trailing newline (D4).
- **`find_markers` fence-awareness** (`document.py:28-55`): shares one fence model with
  `parse_headings`; marker-in-fence ignored; unterminated fence before the open marker
  yields `MissingMarkersError`; double-open / close-before-open raise
  `MalformedMarkersError`.
- **`build_toc`** (`document.py:58-78`): leading-H1 drop before the absolute-level
  `max_depth` filter, `base = min(kept levels)` relative indentation, one shared `used`
  set; `max_depth` 0/negative yields an empty region without crashing.
- **Slug `_1`/`_2` fidelity** (`slug.py`): faithful copy of Python-Markdown incl. the
  anchored `IDCOUNT_RE`; dev-only cross-check against the real `markdown` package passes.
- **`_atomic_write`** (`cli.py:18-41`): same-directory temp + `os.replace` (never
  cross-device), `realpath` preserves symlink semantics, best-effort mode copy, temp
  unlinked on `OSError`. No meaningful TOCTOU for a single-shot CLI on a user-owned file.

## Surgical-diff audit
Clean. Every module, function, and flag traces to the design and D1–D9. Exactly four
modules (`toc.py`/`errors.py` folded into `document.py` per D8). No speculative
abstraction, no unrequested configurability, no orphaned imports or dead code
(`os`/`stat`/`tempfile` in `cli.py` are all used by the atomic writer). Exit codes exactly
0/1/2 (D6), with `1` reachable only under `--check`.

## Simplicity
Appropriate. ~150 lines for a ~150-line tool; functions-over-classes throughout; the only
state is the explicitly-threaded slug set. `_atomic_write` is the one non-trivial block
and is justified (corruption safety) and no larger than needed.

## Security
One advisory (vibe-security-auditor), no blockers/risks. The `_atomic_write` path is
sound — `mkstemp` gives an unpredictable `0600` file with no fd leak, `os.replace` is
same-filesystem by construction (temp created in the resolved target's dir), the `chmod`
only ever widens from `0600` to the source mode (no world-readable window), and symlink
handling via `realpath` is no worse than a plain in-place write. **Advisory:** temp-file
cleanup is scoped to `OSError`, so a `BaseException` (Ctrl-C mid-write, MemoryError) can
orphan a temp file — hygiene only; the original file is untouched until `os.replace`.
See `findings.json`.

## Conventions & docs
Accurate. README matches actual behavior (exit-code table 0/1/2, Python-Markdown slug
style with `_1`/`_2`, the idempotence/`--check` invariant, ATX-only + CRLF→LF +
inline-markup limitations) and fences its own marker example so mdtoc doesn't self-manage
the README. Docstrings present and precise on every module and public function.
Black/isort/119-char clean.

## Verdict
**APPROVE — clean.** 0 blocker, 0 risk, 1 advisory. vibe-code-reviewer returned zero
findings ("a genuinely clean greenfield delivery"); the single advisory is optional
temp-file-cleanup hardening. 83 tests pass, format gate green. Nothing routes back to
`plan` or `build`. CI semantics: exit 0 (no blockers).

### Remediation (optional)
- [advisory] `cli.py:36` — broaden `_atomic_write`'s cleanup from `except OSError` to
  `BaseException` (unlink then re-raise), or a `try/finally`, so an interrupt mid-write
  can't orphan a temp file.
