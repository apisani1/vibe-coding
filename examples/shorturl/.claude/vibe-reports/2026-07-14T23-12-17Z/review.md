# Review (incremental #2) — URL Shortener Service

Prior full review: ../2026-07-14T18-52-16Z/ (PASS, 5 advisories)
Scope: the **delta** since that review — CP9 (`api.py` auth-gate bytes compare + test) and CP10
(`pyproject.toml` drop types-pyyaml, `uv.lock` added). Unchanged modules were not re-read.
Sub-agents: vibe-code-reviewer, vibe-security-auditor (both focused on the delta).

## Verdict: PASS — delta clean, no new findings

Both reviewers independently confirmed the two remediation checkpoints are correct, minimal,
and in scope, and that they introduce nothing new.

## Blockers / Risks

None.

## Delta review

**CP9 — auth-gate bytes compare (`api.py:62-66`).** Correct and *total*: both operands are
`str` from trusted sources, and `str.encode("utf-8")` cannot raise, so the
`hmac.compare_digest` TypeError→500 path is genuinely eliminated (not shifted). All contracted
behaviors preserved — 401 missing / 403 wrong / 403 unconfigured / pass correct / public
redirect. Constant-time property intact (compare on bytes leaks only length difference, as
before — inherent and acceptable). Key still never logged. `test_non_ascii_key_fails_closed_403`
exercises the exact high-byte input that used to 500 and asserts 403 + no state change. The
inline comment documents *why*, which stops a future editor "simplifying" it back to the
crashing form.

**CP10 — dependency hygiene (`pyproject.toml`, `uv.lock`).** Dropping `types-pyyaml` is safe —
`grep -rni yaml` across src/tests/pyproject returns nothing and no yaml package is in the lock.
`uv.lock` (90 KB) is well-formed: **every entry is registry-sourced (pypi.org) and sha256-pinned**,
the only non-registry source is the project itself (editable), and there are no git/path/URL/
install-script sources — a fresh install is now reproducible. (Non-finding: mypy 2.3.0 pulls new
dev-only transitive deps `ast-serialize`, `librt` — registry, hash-pinned.)

## Prior 5 advisories — current status

| # | Advisory | Status |
|---|----------|--------|
| 1 | non-ASCII API key → 500 | **CLOSED** (CP9 bytes compare + regression test) |
| 2 | unused types-pyyaml dev dep | **CLOSED** (CP10 removal; no yaml imports) |
| 3 | dep floors / no lockfile | **CLOSED** (uv.lock present + reproducible; optional `<4` caps not added — a "consider", waivable) |
| 4 | no MAX_CONTENT_LENGTH | open (deferred — authenticated-only, defense-in-depth) |
| 5 | Referer/UA stored + echoed | open (deferred — safe as JSON; latent only with a future HTML UI) |

## Route

**Clean review → ship-ready.** No blocker; nothing routes back to `plan`/`build`. Only the two
defense-in-depth advisories (#4, #5) remain, both consciously deferred. The MVP is now built,
verified (15/15 ACs, 87 tests), and reviewed twice with every high/medium-value finding closed.

Optional finishing touches (approval-gated): `git init` + initial commit (`.gitignore` + `uv.lock`
ready), or `env` to persist a repo CLAUDE.md.
