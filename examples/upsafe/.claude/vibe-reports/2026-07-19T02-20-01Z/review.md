# Review (security-hardening pass)

Scope: the security diff added after the initial commit (90a7d10) — `middleware.py` (new),
`app.py` (middleware wiring + reject-logging exception handler), `__main__.py`
(`access_log=False`), and the new/changed tests. The rest of the service was reviewed clean
at 2026-07-18T22-37-56Z. Sub-agent: **vibe-code-reviewer**. Security folded forward from the
skeptical fresh audit at verify 2026-07-19T02-02-08Z + inline check of the VF-7 delta.

## Verdict: APPROVE — 0 blockers, 0 risks, 0 new findings on the security diff

vibe-code-reviewer read the new/changed source in full and verified the load-bearing
assumptions against the installed Starlette:

- **Middleware correctness (subtle, confirmed):** `_BodyTooLarge` raised in `limited_receive`
  propagates through `ExceptionMiddleware` (no handler → re-raised) and is caught by the
  middleware *before* `ServerErrorMiddleware` can 500 it → clean 413, `response_started`
  False. Non-http scopes pass through; `http.disconnect`/other messages ignored by the
  counter; multi-chunk accumulation correct.
- **Content-Length fast path is defense-in-depth only:** a spoofed/short/malformed length
  `break`s (not `return`s) to the streaming counter, so it cannot bypass the cap; `>` strict
  leaves `store_stream` as the exact arbiter.
- **Exception handler:** delegating to `fastapi.exception_handlers.http_exception_handler`
  preserves the default JSON body + `exc.headers`; `_route_label` reads `route.path_format`
  (template) and falls back to `<unmatched>` — can never surface a concrete path/token.
- **Redaction confirmed:** reject logging emits only method + route template + status; the
  middleware's 413 uses a fixed `<body-too-large>` label. Pinned by
  `test_rejected_upload_is_logged_without_secrets` and
  `test_download_404_logs_route_template_not_token`.
- **Surgical:** ~40-line middleware, no speculative config, no unrelated churn, no
  double-logging (success in routes, rejects once via handler or middleware — disjoint).
- **Docs:** D10 accurate; README's "enforced while streaming" is now genuinely true.

## Standing advisory backlog (carried forward, all accepted/deferred — none new this pass)

- **R-2 (correctness)** — sqlite insert/get run synchronously in async handlers (MVP-fine).
- **R-3 (correctness)** — oversized non-file *field* → 413 not 400 (nit; nothing persisted).
- **S-1 (simplicity)** — `resolve_type` re-checks ext already ensured by `check_extension`
  in the upload path (kept for standalone reuse).
- **VF-5 (security)** — head-only (8 KiB) content validation (contained by attachment+nosniff).
- **VF-6 (dependency)** — open dep floors (mitigated by committed uv.lock).
- **VF-8 (tests)** — middleware streaming→413 path only unit-tested (TestClient sets CL).
- **VF-9 (security)** — no expiry reaper (unbounded disk; documented MVP deferral).

## Route

**Clean review → done.** No blockers/risks route back to plan/build. All prior risk-level
findings (VF-1, VF-4, VF-7, D-1, R-1) are closed; the standing items are accept-and-document.
The service is spec-complete and hardened. Ready to commit/ship.
