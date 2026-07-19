# Review

Scope: full greenfield build (src/upsafe/*.py + tests/*.py, ~890 + ~850 LOC) against
spec (17-03-13Z), design/decisions (17-09-56Z), plan (17-30-16Z) and the build-log trail.
Sub-agent: **vibe-code-reviewer**. Security folded forward from the verify
vibe-security-auditor pass (21-59-33Z) + inline check of the VF-1/VF-4 follow-up delta.

## Verdict: APPROVE — 0 blockers, 0 risks, 7 advisories

Clean, disciplined build. Every module traces to the design's module table; the
security-critical orderings are implemented as specified; lint/type/tests all green
(102 passed, pylint 10.00/10, mypy --strict clean).

## Blockers

None.

## Correctness

Verified sound by the reviewer (read against design + installed Starlette source):
- **Upload ordering** matches design: auth → streaming multipart (`max_part_size`) →
  extension → head-sniff + `seek(0)` → `store_stream` (threadpool) → publish-then-insert
  with `open_within_root(...).unlink(missing_ok=True)` cleanup on insert failure (D4/D9).
  No dangling-capability path.
- **`store_stream`**: temp → `fsync` → atomic `rename` → dir-`fsync`; `BaseException`
  cleanup unlinks the published-or-temp file. Size guard uses `>`; Starlette also uses `>`
  — no off-by-one, a file exactly at the limit is accepted by both.
- **Expiry** is timezone-aware end-to-end (aware `utcnow()` vs aware `fromisoformat`) — no
  naive/aware bug. Unknown and expired both → `None` → identical 404 (criterion 8).
- **`content_disposition`** strips CR/LF/`;`/quotes/path-seps + percent-encodes
  `filename*` (criterion 11). **`is_safe_text`** checks control bytes then incremental
  UTF-8 decode with `final=False` (tolerates a split multibyte at 8192; still rejects
  invalid sequences).
- **`open_within_root`** fail-closed on empty/`.`/`..`/separators + `root in parents`.

Advisory findings (all non-blocking):
- **R-1 (correctness):** 413-vs-400 relies on the `'maximum size'` substring in Starlette's
  exception text — correct against pinned 1.3.1 but message-coupled. → add a regression test
  that asserts 413 on a real oversize part.
- **R-2 (correctness):** sqlite insert/get run synchronously in the async handlers (only
  `store_stream` is offloaded) — MVP-acceptable, latent throughput ceiling under concurrency.
- **R-3 (correctness):** oversized non-file *field* maps to 413 not 400 (shares the substring)
  — semantics nit, nothing persisted.

## Surgical-diff audit

- **One true orphan: `errors.TooManyParts`** (defined, referenced nowhere — grep-confirmed).
  The multi-part case is handled by Starlette `max_files` (→400) and the `len(files)!=1`
  guard. → **D-1: delete it** (or actually raise it at routes.py:97-98). This is the one
  cleanup worth doing.
- The `errors.py`/`Makefile`/`pyproject`/formatting scope expansions all carry logged human
  approval in the plan (flagged live by vibe-overseer during build) — not drive-by.
- `enable_docs` traces to verify-finding VF-4. No speculative abstraction, no dead config.

## Simplicity

- **S-1:** `resolve_type` re-checks `ext not in allowed_types` that `check_extension`
  already guaranteed in the upload path. Harmless; defensible if `resolve_type` is used
  standalone. Not worth churn.
- Overall: no over-engineering. Modules are small and single-responsibility; `routes.py`
  (192 LOC) is the largest and is mostly linear orchestration.

## Security (folded forward + delta check)

The verify vibe-security-auditor found no blockers/risks and confirmed structural
path-traversal defense, streaming size cap + DoS bounds, constant-time key compare, 256-bit
opacity, redacting logs, secure defaults, attachment+nosniff+sanitized disposition, and
parameterized SQLite. **VF-4 (unauthenticated docs) is now closed.** The VF-1/VF-4 follow-up
code (config `_bool`, `app.py` docs flag) was inline-reviewed here: default-off, fail-closed
on invalid boolean, explicitly typed — no concern. Two hardening advisories remain:
- **VF-5 (security):** head-only content validation (contained by attachment + nosniff).
- **VF-6 (dependency):** open dep floors (mitigated by committed uv.lock).

## Conventions & docs

Functions-over-classes honored (classes only for `Settings`/`StoredObject`/`UploadResponse`
data + errors); type annotations on public functions; no bare `except`; docstrings
consistently explain *why* (durability ordering, token separation). README + `.env.example`
are current (the docs flag was documented in the follow-up build). No stale docs found.

## Praiseworthy (keep these)

- Two-CSPRNG separation of download token vs on-disk name (D3) — the right structural defense.
- `logging.py` redacting-by-construction (keyword-only field allow-list, route template not
  concrete path) — correct way to own criterion 10.
- Frozen `Settings` injected into `create_app` — construction separate from use, fully
  testable against `tmp_path`.

## Route

**Clean review → done.** No blockers route back to `plan`/`build`. The 7 advisories are
optional polish; the single one worth a quick follow-up `build` is **D-1 (delete dead
`TooManyParts`)** — a pure orphan removal. R-1 (a 413 regression test) is the next most
useful. Everything else is accept-and-document.
