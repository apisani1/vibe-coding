# Verify — FinAlly, after checkpoints 18 and 19

**Run:** 2026-08-21T01-27-50Z · **Target:** `/Users/antonio/AI/MyCode/vibe-coding-course/fin`
**Upstream:** plan `2026-08-13T23-18-51Z` (19 checkpoints, all approved) · review `2026-08-17T08-59-28Z`
**Sub-agents:** none — this run re-executes the verification plan directly.

## Why this run exists

`latest` pointed at the **review** run and still announced *"2 blockers, 5 risks, 13
advisories — routes back to build."* That was true on 2026-08-17 and has been false since:
CP18 closed the blockers and risks, CP19 closed the advisories, and an E2E defect found
tonight retracted a claim in the build log. Anyone reading `latest` was reading the project as
it stood two checkpoints ago.

## Result

| | |
| --- | --- |
| **Blockers** | 0 |
| **Risks** | 0 |
| **Advisories** | 2 open (below) |
| **Gate D** | **green**, including GD3 for the first time since 2026-08-16 |

## Checks executed

| Check | Verdict | Evidence |
| --- | --- | --- |
| **A1** secret scan over all history | **PASS** | 106 commits. Shape needle `sk-[A-Za-z0-9_-]{8,}`: no blob. Live-key value needle: no blob. `.env` untracked and ignored by `.gitignore:4 .env*`. **Positive control found `SPEC.md`**, so the scan can still find things. |
| **A2–A13** static gates | **PASS** | `mypy --strict` clean over 31 files; flake8 clean; black and isort clean; **pylint 10.00/10**. |
| **A14** chat rate limit *(new at CP19)* | **PASS** | 8 cases. Burst refused at the 11th; `Retry-After` checked from both sides; refill one-at-a-time; idle hour banks nothing; rewound clock mints nothing; endpoint 429s; a refused turn is not persisted; two apps do not share a bucket. |
| **B1–B7** service and orchestration | **PASS** | Part of the 285. |
| **B8** the seed is one transaction *(new)* | **PASS** | A mid-seed failure leaves no profile row. |
| **B9** a dust buy writes nothing *(new)* | **PASS** | Refused; trades, positions and snapshots all empty; cash unmoved. |
| **B10** a 503 leaves the transcript answered *(new)* | **PASS** | User row **and** assistant row, status still 503, reason never a provider's string. |
| **C1–C7** frontend | **PASS** | 173 tests across 16 files; `tsc --noEmit` clean; eslint clean. |
| **GD1, GD2** image and scripts | **PASS** | Image rebuilt tonight; `/app/db` present and empty in-image; the running container publishes `127.0.0.1:8000` with `finally-data` attached. |
| **GD3** E2E from a cold compose | **PASS — and see the correction below** | **21 passed (21.6s)**, exit 0, no tracebacks, clean teardown. Valid **only** because the image was forced to rebuild. |
| **GD4, GD5** docs parity, `make check` | **PASS** | Environment surface matches `.env.example`; sweep green. |
| **GD6** a chat turn does not stop the event loop | **PASS** | In the 285. *(Defined in `tests/test_event_loop.py`; never transcribed into the verification plan — noted there now.)* |
| **GD7** docs surface removed, table replaced it *(new)* | **PASS** | `/docs`, `/redoc`, `/openapi.json` → 404 in both arrangements; endpoint table present. |

### Live probes against the running container

Read-only throughout: the container's startup line reads `llm: live via OpenRouter,
model=openai/gpt-oss-120b`, so `/api/chat` was **not** touched — a single POST would have been
a billable call, and this run's budget of one was spent at CP2.

| Probe | Result |
| --- | --- |
| `GET /api/health` | 200 |
| `Host: evil.example.com` | **400** — CP18's DNS-rebinding guard, live for the first time |
| `Host:` localhost / localhost:8000 / 127.0.0.1 | 200, 200, 200 |
| `/docs`, `/redoc`, `/openapi.json` | 404 `text/html` (the export's 404 page) |
| `/api/definitely-not-a-route` | 404 `application/json` |
| `http://192.168.1.184:8000/api/health` from the host's own LAN address | **refused** — loopback binding proven from a real LAN IP, not from the flag |
| `GET /api/portfolio` | `total_value == cash_balance + positions_value` holds; 4 positions, 10 watchlist rows — the volume survived the rebuild |

### Image contents, checked in the artefact rather than the Dockerfile

`TrustedHostMiddleware` 2 · `chat_limiter` 1 · `openapi_url=None` 1 · `api/ratelimit.py`
present · `read_transaction` 1 · `DustQuantity` 1 · **`llm/spike.py` absent**.

## The correction this run exists to record

The first E2E attempt tonight passed — **21 specs, 22.0s — against an image built four days
earlier.** `docker compose up` builds only when the image is *missing*, and `finally:e2e`
existed. It was noticed because one startup line was absent: `_log_startup_configuration`
emits three, the container printed two, and the missing one was `allowed hosts:` — added at
CP18. Confirmed by grepping the image: **0** `TrustedHostMiddleware`, **0** `chat_limiter`.

Consequence, stated rather than buried: **CP18's build-log claim of "21 E2E specs still green
from a cold compose" was not earned and is retracted.** "Cold compose" was true of the
containers and false of the image. The same applies to the Gate D re-run at
`2026-08-17T04-53-00Z`, though CP17 was documentation and a Makefile target.

Re-run with `--build`, the suite passes for real, and every GD3 claim above rests on that run.

## Open items

Two, both requiring a human decision because the plan's `max_checkpoints: 19` is spent.

1. **`make e2e` does not force a rebuild** — one line (`up --build`). Until it changes, the
   next run can repeat exactly the failure above.
2. **litellm stays** — D26, ratified by Antonio. Not a defect; recorded so the dependency
   audit has a standing entry.

## Cannot be verified, unchanged

The Massive real-data path has never run against the live API; a mid-session SSE cut is not
stageable from Playwright; and nothing here asserts the UI looks good. The one live LLM call
remains spent at CP2 — **no live call was made in this run**.
