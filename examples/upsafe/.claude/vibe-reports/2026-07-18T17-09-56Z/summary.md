# Summary — design

- **Mode:** design
- **Target:** /Users/antonio/AI/MyCode/upsafe (bare greenfield)
- **Run dir:** .claude/vibe-reports/2026-07-18T17-09-56Z
- **Upstream:** .claude/vibe-reports/2026-07-18T17-03-13Z (spec.md)

## What the design says

FastAPI app, three routes (`POST /uploads`, `GET /downloads/{token}`, `GET /healthz`),
flat set of small single-responsibility modules under `src/upsafe/`. One data root holds
a `quarantine/` dir + `upsafe.db` (SQLite). Security posture is structural:

- Path traversal impossible by construction — no client string is a path component;
  on-disk `stored_name` and the download `token` are two independent CSPRNG values, the
  token only ever a DB key.
- Streaming size cap via Starlette `max_part_size` (+ redundant byte counter).
- Two-layer type validation: extension allow-list AND content-signature (hand-rolled
  table) / strict text-safety; server-resolved `content_type` stored, not client's.
- Atomic publish: temp → fsync → rename → **fsync dir** → commit metadata (crash-safe).
- Redacting structured logging owns the "no secret leakage" criterion.

## Sub-agents used

- **vibe-architect** (user scope, model inherit) — documents-only review.

## Architect findings folded in

- **risk** — no logging owner for acceptance criterion 10 → added `logging.py` module +
  redaction contract (D8).
- **risk** — crash-consistency claim stronger than mechanism → added quarantine-dir
  `fsync` before metadata commit (D9).
- **advisory** — text-safety anti-`<` heuristic could false-positive → demoted to
  optional defense-in-depth; UTF-8/NUL/control is the load-bearing guard (D1 note).
- **advisory** — Starlette spool-threshold also bounds memory → named as a second pinned
  behavior; criterion-4 test asserts a concrete peak-memory bound.

Architect's overall verdict: strong, not over-engineered; core security claims sound;
no design drift beyond the (well-justified, documented) zero-byte rejection.

## Artifacts

- `design.md` — overview, data model (erDiagram), module/component design (flowchart),
  algorithms & libraries, edge cases, ripple effects, broader context.
- `decisions.md` — D1–D9 with alternatives and consequences.

## Next

`plan` (read-only) — will load this `design.md`, produce `plan.md` + `checklist.md` +
`verification-plan.md` (verification written before any code), and dispatch
**vibe-test-designer**. No repo mutation until `build`, which requires explicit written
per-checkpoint approval.
