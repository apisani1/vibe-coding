# Verify — summary

- **Mode:** verify · **Target:** `/Users/antonio/AI/MyCode/vibe-coding-course/fin`
- **Run:** `2026-08-21T01-27-50Z` · **Sub-agents:** none
- **Result:** **PASS — 0 blockers, 0 risks, 2 advisories.** Gate D green, including GD3 for the
  first time since 2026-08-16.

## Why this run exists

`latest` still announced *"2 blockers, 5 risks, 13 advisories — routes back to build"* from
2026-08-17. Two checkpoints have landed since and one recorded claim turned out to be false.

## Where the review's 20 findings ended up

| | |
| --- | --- |
| 2 blockers | fixed at CP18 |
| 5 risks | fixed at CP18 |
| 13 advisories | 12 fixed at CP19; **litellm kept**, ratified as D26 |

## The correction

Tonight's first E2E run passed — **and tested an image built four days earlier.**
`docker compose up` rebuilds only when the image is missing. It was caught because one
startup line was absent from the container output (`allowed hosts:`, added at CP18), then
confirmed by grepping the image: 0 `TrustedHostMiddleware`, 0 `chat_limiter`.

**CP18's claim of "21 E2E specs still green from a cold compose" is retracted.** Re-run with
`--build`, the suite genuinely passes: 21 in 21.6s, clean teardown, and the image verifiably
contains CP18 and CP19 with `llm/spike.py` absent.

## Numbers, as of this run

285 backend tests · 173 frontend · `mypy --strict` over 31 files · flake8, black, isort clean ·
**pylint 10.00/10** · **21 E2E specs** · A1 clean over **106 commits** with its positive
control intact · **0 live LLM calls**.

Live against the running container: `Host: evil.example.com` → **400**; the host's own LAN
address → **refused**; `/docs` → 404; `total_value == cash + positions` holds.

## Open

Both advisories this run raised are now closed; one new one came out of closing them.

| | Status |
| --- | --- |
| `make e2e` lacked `--build` | **fixed at CP20** (`dad9e19`), GD8 pins it |
| README's stale-image trap | **fixed at CP21** (`88553ab`), GD9 pins it — approved on the third pass |
| litellm | **no change needed** — ratified as D26 |
| **The start scripts' early exit** | **open, needs the human** |

The new one is the sharp one. `./scripts/start_mac.sh --build` builds the image and *then*
checks whether a container is already running; if one is, it prints `FinAlly is already
running`, exits 0, and keeps serving the old container. CP21 **documented** that. Making the
branch say the new image is not what is being served is what would **close** it — a code change
to the script that starts a live container, so it is Antonio's call.

## Next

No pipeline mode is outstanding.
