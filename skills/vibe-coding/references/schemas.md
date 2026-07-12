# Schemas

Machine-readable contracts: `findings.json`, `state.json`, and the sub-agent return
contract with merge rules. All JSON is pretty-printed with 2-space indent.

## Contents

- [findings.json](#findingsjson)
- [Category allow-list](#category-allow-list)
- [Severity semantics](#severity-semantics)
- [state.json](#statejson)
- [Sub-agent invocation & return contract](#sub-agent-invocation--return-contract)
- [Merge rules](#merge-rules)
- [CI exit codes](#ci-exit-codes)

## findings.json

Emitted by `verify` and `review` (only). Canonical shape:

```json
{
  "mode": "verify",
  "scanned_at": "2026-07-09T14:30:00Z",
  "target": "/abs/path/to/repo",
  "subagents_used": ["vibe-test-designer"],
  "findings": [
    {
      "category": "tests",
      "severity": "risk",
      "file": "src/photodedupe/scan.py",
      "line": 42,
      "checkpoint": "3.2",
      "message": "Acceptance criterion 'corrupt file is skipped with a warning' has no covering check",
      "remediation": "Add a unit test feeding a truncated JPEG to scan_dir()",
      "agent": "vibe-test-designer"
    }
  ]
}
```

Field notes:

| Field           | Required | Notes                                                                    |
| ---------------- | -------- | ------------------------------------------------------------------------ |
| `mode`           | yes      | `verify` or `review`.                                                    |
| `scanned_at`     | yes      | UTC ISO-8601.                                                            |
| `target`         | yes      | Absolute repo path.                                                      |
| `subagents_used` | yes      | Names actually dispatched this run; `[]` if all inline.                  |
| `category`       | yes      | From the allow-list below — never invented.                              |
| `severity`       | yes      | `blocker` \| `risk` \| `advisory`.                                       |
| `file` / `line`  | no       | Omit for repo-wide or process findings (e.g. "no check covers X").       |
| `checkpoint`     | no       | Checkpoint id from `checklist.md` when the finding traces to one.        |
| `message`        | yes      | What is wrong / observed, specific enough to act on.                     |
| `remediation`    | yes      | The concrete next action.                                                |
| `agent`          | yes      | Producing sub-agent name, or `"inline"`.                                 |

## Category allow-list

Strict — a finding whose `category` is not in this table is invalid. If a finding
doesn't fit, pick the closest category and explain the nuance in `message`; never coin
a new one inline. (This table is authoritative; the SKILL.md summary is a projection —
keep them in sync.)

| Category       | What it captures                                                             | Typical producer            |
| -------------- | ----------------------------------------------------------------------------- | ---------------------------- |
| `correctness`  | Bugs, logic errors, unhandled edge cases, broken contracts                    | vibe-code-reviewer / inline  |
| `tests`        | Missing/weak/failing verification; acceptance criteria without covering checks | vibe-test-designer / inline  |
| `simplicity`   | Over-engineering: speculative abstraction, unrequested flexibility, bloat     | vibe-architect, vibe-code-reviewer |
| `security`     | Input validation, secrets, injection surfaces, unsafe defaults                | vibe-security-auditor / inline |
| `design-drift` | Built/designed thing diverges from spec or plan; untraceable changed lines    | vibe-architect, vibe-code-reviewer |
| `docs`         | Documentation the change should have created/updated                          | vibe-code-reviewer / inline  |
| `dependency`   | Unpinned/risky dependencies, floors/caps, supply-chain hygiene                | vibe-security-auditor / inline |
| `advisory`     | Opportunity, not a problem — worth-adopting improvements, moonshot notes      | any                          |

## Severity semantics

- `blocker` — an acceptance criterion is unmet or unverifiable, behavior is broken, or
  a security issue is **exploitable now**. CI exit 1.
- `risk` — likely to surface latent issues: fragile logic, coverage gap on a risky
  path, hardening needed.
- `advisory` — opportunity, not a problem.

Grade against the spec's acceptance criteria, not abstract severity taste: the same
missing test is a `blocker` if it guards an acceptance criterion and `risk` otherwise.

## state.json

Written by every run-dir mode (not `ask`; `build` updates the existing one in place).
This is what makes runs chainable and auditable:

```json
{
  "mode": "plan",
  "created_at": "2026-07-09T14:30:00Z",
  "target": "/abs/path/to/repo",
  "greenfield": false,
  "scope": "photo-dedupe CLI, MVP per spec",
  "upstream_run": "2026-07-09T13-05-11Z",
  "upstream_artifacts": ["design.md", "decisions.md"],
  "subagents_used": ["vibe-test-designer"],
  "artifacts": ["plan.md", "checklist.md", "verification-plan.md", "summary.md"],
  "build": {
    "approvals": ["2026-07-09T15:02:44Z checkpoint-1..2 — 'Yes, implement checkpoints 1 and 2'"],
    "completed_checkpoints": ["1", "2"],
    "last_updated": "2026-07-09T15:41:09Z",
    "auto": {
      "granted_at": "2026-07-09T15:00:00Z",
      "grant_quote": "/vibe build --auto",
      "max_checkpoints": 10
    }
  }
}
```

The `build.auto` object exists only for `--auto` runs: `grant_quote` is the user's
invocation verbatim (it is the written approval of record), and `max_checkpoints`
comes from `.claude/vibe-coding.local.md` `auto_max_checkpoints` (default 10).

`upstream_run` is the run-dir name consumed (or `null`). The `build` object exists only
after `build` has run against this dir. When a mode loads its upstream from an explicit
path rather than `latest`, record that path — the chain must reflect what was actually
read.

## Sub-agent invocation & return contract

**Invocation** (in the Task-tool message to the agent):

```
repo_path: <absolute path to target repo>
run_dir: <absolute path to the current run dir>
artifact_paths: <the upstream artifacts this agent must read, absolute paths>
scope_glob: <default **/*; narrow for monorepos>
task: <one paragraph: exactly what to analyze and against what ground truth>
model: <optional — from .claude/vibe-coding.local.md; apply where the harness
        supports a per-dispatch model override, otherwise record the request in
        summary.md and advise setting the agent file's model: frontmatter. Never
        edit agent files silently.>
```

**Return.** The agent's reply MUST begin with one fenced ```json block:

```json
{
  "agent": "vibe-architect",
  "findings": [ { "...": "same finding shape as findings.json, without the agent field or with it — see merge rules" } ]
}
```

followed by a human-readable narrative. The orchestrator parses only the first fenced
JSON block; the narrative is for humans. An agent with nothing to report returns
`"findings": []` — an empty block is a valid, meaningful result.

In `design` and `plan` modes the sub-agent's primary product is prose/structure (a
design critique, a drafted verification plan) — there the narrative carries the
payload and `findings` carries only the issues found.

**vibe-overseer verdict contract** (`--auto` builds only). The overseer's fenced JSON
adds a `verdict`:

```json
{
  "agent": "vibe-overseer",
  "verdict": "approve",
  "reasons": ["checkpoint 2 diff matches Touches; verify check passed with evidence"],
  "findings": []
}
```

`verdict` is `"approve"` or `"reject"` — nothing else. `reasons` is a non-empty list of
plain-language justifications. `findings` uses the standard finding shape (allow-list
categories) for anything worth recording regardless of verdict. A `reject` verdict or
any blocker-severity finding stops the autopilot run. A malformed or missing verdict
block is treated as `reject` (fail closed).

## Merge rules

When merging sub-agent findings into the run's `findings.json`:

1. Validate each finding: `category` in the allow-list, `severity` valid, `message`
   and `remediation` non-empty. Drop invalid ones and note the drop in `summary.md`.
2. Prepend/overwrite `"agent": "<agent name>"` on every finding from that agent.
3. Dedupe on (`file`, `line`, `category`): keep the higher severity; merge
   `message` texts when they add information.
4. Append inline findings last, with `"agent": "inline"`.
5. Sort: severity (`blocker` → `risk` → `advisory`), then `file`, then `line`.
6. Update `subagents_used` to exactly the set that was dispatched **and returned a
   parseable block** — an agent that errored or returned no JSON is not "used"; rerun
   its category inline.

## CI exit codes

| Exit | Meaning                                                       |
| ---- | -------------------------------------------------------------- |
| 0    | Clean, or `risk`/`advisory` findings only                      |
| 1    | At least one `blocker` finding                                  |
| 2    | Config error: unresolved inputs, missing upstream plan, bad target |

`jq` gate equivalent:

```bash
jq -e '[.findings[] | select(.severity == "blocker")] | length == 0' findings.json
```
