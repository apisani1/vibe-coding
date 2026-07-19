# Summary — plan

- **Mode:** plan
- **Target:** /Users/antonio/AI/MyCode/upsafe (bare greenfield)
- **Run dir:** .claude/vibe-reports/2026-07-18T17-30-16Z
- **Upstream:** .claude/vibe-reports/2026-07-18T17-09-56Z (design.md, decisions.md)

## Shape of the plan

8 checkpoints in 3 phases, risky work front-loaded:

- **Phase A — Storage & data foundation** (CP1 scaffold+config+tokens, CP2 metadata,
  CP3 streaming/atomic/traversal-safe storage core). Boundary: `verify`.
- **Phase B — Validation & HTTP surface** (CP4 validation, CP5 auth+logging, CP6 upload
  endpoint, CP7 download+health). Boundary: `verify` against all 12 criteria.
- **Phase C — Hardening & docs** (CP8 adversarial e2e suite + README + `.env.example` +
  clean lint/type gate). Boundary: final `verify` → `review`.

Verification is written **before any code** (`verification-plan.md`), every one of the
12 acceptance criteria mapped to at least one check.

## Sub-agents used

- **vibe-test-designer** (user scope, model inherit) — drafted the verification plan.

## Test-designer findings folded in

- **risk** — criterion 4 ("no whole-body buffer") can't be honestly proven e2e because
  httpx/TestClient buffers the body client-side → moved the *load-bearing* streaming +
  peak-memory proof to CP3 storage layer (counting reader + max-buffer probe); CP6 e2e
  memory bound demoted to secondary/best-effort. Plan CP3 & CP6 updated.
- **risk** — criterion 10 log scan misses uvicorn's access log (not emitted by
  TestClient) → capture app-logger handlers into a buffer with sentinels; production
  access-log redaction declared in "Cannot be verified".
- **risk** — criterion 5 NUL/control filename may be dropped by the HTTP layer → cover at
  two layers (validation/storage unit + e2e for variants that survive transport).
- **advisory** ×3 — durability only ordering-testable (not real crash); token-opacity
  timing not testable (code-inspection only); the optional `<` text flag must not be
  asserted as a hard criterion-3 gate.

## Artifacts

- `plan.md` — risk factors, 8 checkpoints, 3 phases, Definition of Done.
- `checklist.md` — one line per checkpoint + phase boundaries, unticked.
- `verification-plan.md` — criteria, checks (by layer), external signals, risk-based
  expansion, and an explicit "Cannot be verified" section.

## Next

`build` — **the first repo-mutating mode.** Operates in place on this run dir; requires
**explicit, written, per-checkpoint approval** before each mutation ("Yes, implement
checkpoint 1"). Checkpoint 0 will propose seeding the bare repo from your preference
profile assets (add-only). Vague "ok/sure" is not approval. `--auto` autopilot is
available (vibe-overseer is installed) if you want an approved autonomous run.
