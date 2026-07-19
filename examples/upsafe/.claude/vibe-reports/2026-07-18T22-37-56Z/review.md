# Review (re-review)

Scope: full build after the D-1/R-1 follow-up. Prior full review: 2026-07-18T22-19-54Z
(vibe-code-reviewer read the whole tree). This re-review confirms the two closures and
re-checks the small delta inline; no full re-audit dispatched (delta = 1 dead-code deletion
+ 3 test additions, no behavior change).

## Verdict: APPROVE — 0 blockers, 0 risks, 5 advisories (was 7)

## Blockers

None.

## Closed since last review

- **D-1 (design-drift)** — `errors.TooManyParts` deleted; `errors.py` now holds only
  exceptions that map to a status. Grep confirms zero references in src/ or tests/. The
  surgical-diff audit's only orphan is gone.
- **R-1 (correctness)** — the 413-vs-400 message coupling is now guarded by 3 unit tests
  on `_too_large_or_bad_request` (size → 413; too-many-files/fields → 400), complementing
  the live-parser e2e oversize(413)/multi-file(400) tests. A Starlette reword within the
  pin now fails loudly.

## Remaining advisories (accepted / documented)

- **R-2 (correctness)** — sqlite insert/get run synchronously in async handlers (only
  `store_stream` is offloaded). MVP-acceptable; latent throughput ceiling under concurrency.
- **R-3 (correctness)** — oversized non-file *field* → 413 not 400 (shares the "maximum
  size" substring). UX nit; nothing persisted.
- **S-1 (simplicity)** — `resolve_type` re-checks `ext in allowed_types` already ensured by
  `check_extension` in the upload path. Kept intentionally for standalone reuse of
  `resolve_type`.
- **VF-5 (security)** — head-only (8 KiB) content validation; contained by attachment+nosniff.
- **VF-6 (dependency)** — open dep floors; mitigated by committed uv.lock.

## Delta re-check (inline)

`errors.py`: removal is clean, imports elsewhere unaffected (`routes.py` imports only
`EmptyUpload, FileTooLarge, TypeNotAllowed`). `tests/test_upload.py`: the 3 new tests import
the private `_too_large_or_bad_request` (tests are excluded from flake8/pylint per config) and
assert the mapping against the exact Starlette 1.3.1 message forms. `make pre-commit` clean,
105 tests pass. No new issues introduced.

## Route

**Clean review → done.** No route-back. All previously-actionable findings are closed; the
5 remaining are accept-and-document.
