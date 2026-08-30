# Review — summary

- **Mode:** review (final pipeline mode)
- **Target:** `/Users/antonio/AI/MyCode/vibe-coding-course/fin`
- **Sub-agents used:** `vibe-code-reviewer`, `vibe-security-auditor`
- **Result:** **2 blockers, 5 risks, 13 advisories** — every blocker and risk reproduced independently before being recorded.

## The two blockers

1. **`POST /api/chat` freezes the event loop.** `handle_message` is `async def` and runs blocking `sqlite3` directly on it — the failure D21 exists to prevent, with `api/chat.py`'s docstring claiming the opposite. Measured: **0 loop beats** during a stalled chat turn versus 162 for the same work through a `def` handler. Every SSE stream and background task stops for the duration.
2. **`buy 0 AAPL` under `LLM_MOCK=true` returns HTTP 500**, orphaning the user's turn in the transcript and in every later prompt. The test named after that value passes because it bypasses validation and monkeypatches the code under test away — the seventh check in this run that could not fail.

## Security

No blockers. The secret boundary holds under independent scrutiny (key absent from all 470 blobs, the built bundle, and the image). D5 survived a hostile-model probe. Three risks: the Massive key can reach the logs via an exception string; no Host validation (DNS rebinding); and the published port binds `0.0.0.0`, making a no-auth app LAN-reachable by default.

## Next

The blockers route back to `build`. One remediation checkpoint covers both blockers, both correctness risks and both network risks — but it is **beyond the 18 checkpoints the plan contains**, so it is the human's call, not the autopilot's.
