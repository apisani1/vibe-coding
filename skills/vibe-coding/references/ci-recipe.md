# CI recipe

vibe-coding ships no CI YAML — pipelines are the user's. Only `verify` and `review`
support headless (`--ci`) operation; the DECIDE modes are interactive by design and
`build` requires human approval, so neither belongs in CI.

## Headless invocation

```bash
# Verify: execute the latest run's verification plan
claude -p "/vibe verify --ci --json" > findings.json

# Review: read-only quality/security pass over the built diff
claude -p "/vibe review --ci --json" > findings.json
```

Inputs resolve from env vars when flags/args are absent: `VIBE_MODE`, `VIBE_TARGET`
(defaults to the working directory).

## Gating

Trust the exit code:

| Exit | Meaning                                     | Suggested CI behavior |
| ---- | -------------------------------------------- | ---------------------- |
| 0    | Clean, or `risk`/`advisory` only             | Pass                   |
| 1    | ≥ 1 `blocker` finding                        | Fail the job           |
| 2    | Config error (no plan/upstream, bad target)  | Fail loudly — misconfiguration, not code quality |

Or gate explicitly with `jq`:

```bash
jq -e '[.findings[] | select(.severity == "blocker")] | length == 0' findings.json
```

To also fail on `risk` (stricter posture for release branches):

```bash
jq -e '[.findings[] | select(.severity != "advisory")] | length == 0' findings.json
```

## Notes

- `verify --ci` needs a run dir containing `verification-plan.md` — i.e. the
  plan/build happened on this branch and `.claude/vibe-reports/` is available to the
  job (committed, or restored as a workflow artifact). Absent → exit 2.
- `review --ci` degrades gracefully without upstream artifacts: it reviews the diff
  against repo conventions and marks the trace-to-spec audit as skipped
  (`summary.md` records this). Provide the run dir for the full audit.
- In CI, sub-agent probing behaves as in interactive mode; agents installed in the
  repo's `.claude/agents/` are used, otherwise inline fallbacks run — results note
  which path was taken (`subagents_used`).
- Publish the run dir (report + `findings.json`) as a build artifact so humans can
  read `verify-report.md` / `review.md`, not just the exit code.
