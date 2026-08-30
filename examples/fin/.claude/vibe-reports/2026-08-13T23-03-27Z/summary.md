# Run summary

- Mode: design
- Target: /Users/antonio/AI/MyCode/vibe-coding-course/fin (bare greenfield)
- Scope: FinAlly — AI trading workstation; technical design for the full MVP per `SPEC.md`
- Upstream run consumed: none — `SPEC.md` at the repo root was consumed directly in place
  of a `define` run (user-authored and decision-complete)
- Sub-agents used: vibe-architect
- Artifacts: design.md, decisions.md, summary.md, state.json
- Findings: n/a (design mode emits no `findings.json`; the architect's 10 findings were
  folded into the artifacts — see below)
- Next: `plan` (read-only — writes only to a new run dir, never to repo code)

## Architect review

`vibe-architect` returned **10 findings: 0 blockers, 7 risk, 3 advisory**. All 10 were
folded into `design.md` / `decisions.md`; none were rejected. The substantive ones:

| # | Finding | Resolution |
| --- | --- | --- |
| 1 | Watchlist "daily change %" had no owner — `previous_price` is a 500 ms delta | Added `session_open` to `Quote`; change % now baselines off it (D19) |
| 2 | Chat history persisted but no route exposed it — panel blank after reload | Added `GET /api/chat/messages` (D18) |
| 3 | Blocking `sqlite3` on the event loop unaddressed; `BEGIN IMMEDIATE` claim unfounded | New "Database access in an async process" section; sync services + threadpool handlers (D21) |
| 4 | Spec §11/§12 deliverables unplaced (Dockerfile, scripts, test compose) | New "Packaging & delivery" section |
| 5 | Frontend unit-test stack absent though spec §12 requires it | Vitest + React Testing Library added |
| 6 | Event-shock rate ~30× the diffusion scale — chart would be a staircase | Shocks re-rated per-minute; elevated σ made explicit (D23) |
| 7 | Main chart had no data source beyond the 60 s sparkline ring | Two-tier buffer, 1,800 points for the selected ticker (D22) |
| 8 | Hand-rolled treemap invented work — Recharts already a dependency | Recharts `Treemap` is now the default (D16) |
| 9 | `asyncio.Lock` on the cache was ceremony in single-threaded asyncio | Removed; atomic dict rebind |
| 10 | Massive poll interval hardcoded despite spec §6 calling it configurable | `MASSIVE_POLL_SECONDS` (D24) |

The architect independently verified the GBM formula and its `−σ²/2` correction, the
one-factor correlation math, weighted-average-cost handling, the SSE change-detection
scheme, and that a Python package cannot be named `finally`.

## Instructions applied over the spec

Two user instructions arrived mid-run and **supersede `SPEC.md` §9**:

1. **No Cerebras provider pinning** — the OpenRouter request names a model and nothing
   else; no `provider.order`, no `allow_fallbacks: false`. (D10)
2. **The model id comes from `OPENROUTER_MODEL`**, with `OPENROUTER_API_KEY` from `.env`.
   No default model is baked into the source. (D9)

Structured Outputs are used as instructed: `response_format` carries a strict
`json_schema` generated from the Pydantic models, which is what lets the backend populate
`trades[]` and `watchlist_changes[]` as typed fields. Because the model is
user-selectable and structured-output support varies across OpenRouter's catalogue, the
parser stays tolerant (fences → outermost braces → Pydantic) while execution stays strict.

## Environment (resolved)

`fin/.env` was copied verbatim from the sibling `finally/` at the user's request
(mode `600`). Contents, keys only:

| Variable | Value | Effect on this design |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | set (`sk-or-v…`, 73 chars) | Chat is live; no 503 path on startup. |
| `OPENROUTER_MODEL` | `openai/gpt-oss-120b` | Passed to LiteLLM as `openrouter/openai/gpt-oss-120b`. D9's no-default rule is satisfied by configuration, not by code. |
| `MASSIVE_API_KEY` | **empty** | Simulator is the active market source — the design's default path. The copied comment records that the prior account's plan returned 403 on `/v2/snapshot`. |
| `LLM_MOCK` | `false` | Live LLM calls. E2E must override to `true` (spec §12) or the suite bills real credits. |

Two carry-overs from the copy for `plan` to handle:

- The file's comment block references `PLAN.md section 5` and `.env.bak-massive`, neither
  of which exists in `fin/`. Harmless, but the comment should be rewritten when
  `.env.example` is authored during `build`.
- **`fin/` has no `.gitignore` and is not yet a git repo.** A live API key is now sitting
  in the project root unprotected. Checkpoint 0 of `build` must create `.gitignore` with
  `.env` in it *before* any `git init`/first commit — this is the one ordering constraint
  in the whole build with a real-world consequence.

## Open questions for `plan`

1. **The `cerebras-inference` skill named in spec §9 is not installed** in this
   environment. Moot given the no-provider-pinning instruction, but worth recording: the
   LLM client is designed directly against LiteLLM rather than against that skill.
2. **The user's second message mentioned "populate fields in the legal document"** — no
   legal document exists in this project. The OpenRouter/structured-output/env-var parts
   of that instruction were applied; the legal-document framing was not, on the assumption
   it carried over from a different context.

## Notes

- The sibling `/Users/antonio/AI/MyCode/vibe-coding-course/finally` is a prior completed
  build of this same spec. It was read as reference only — to sanity-check feasibility,
  not as a convention this design must match. Nothing in it was modified.
- Backend package is `finally_app`, not `finally`: the latter is a Python reserved word
  and unimportable (D15). The product name is unaffected.
