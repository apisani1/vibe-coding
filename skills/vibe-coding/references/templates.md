# Artifact templates

Canonical templates for every artifact vibe-coding emits. Copy the structure; drop
sections that are genuinely empty rather than filling them with boilerplate, and say
`None` where the absence itself is informative (e.g. `Out of scope: none identified`
is a smell — push the interview harder).

## Contents

- [spec.md](#specmd) (`define`)
- [design.md](#designmd) (`design`)
- [decisions.md](#decisionsmd) (`design`)
- [plan.md](#planmd) (`plan`)
- [checklist.md](#checklistmd) (`plan`, ticked by `build`)
- [verification-plan.md](#verification-planmd) (`plan`)
- [build-log.md](#build-logmd) (`build`)
- [verify-report.md](#verify-reportmd) (`verify`)
- [review.md](#reviewmd) (`review`)
- [env-report.md](#env-reportmd) (`env`)
- [CLAUDE.md template](#claudemd-template) (`env`)
- [summary.md](#summarymd) (all run-dir modes)

---

## spec.md

```markdown
# Spec: <short title>

## Goal
<the real outcome, decision, or user value — one paragraph. ArjanCodes step 1: what is
it, who is it for, what problem does it solve, how will it work>

## Main concepts
<the domain concepts involved and how they relate — a short list or a Mermaid diagram>

## Users & user stories
<ArjanCodes step 2. Happy flows AND alternative flows, as "As a <user>, I … so that …".
For a feature in an existing app: impact on the overall interface/structure.>

## Scope
- In (MVP): <the minimum needed to test whether this is useful>
- Out: <explicitly deferred — with one-line reasons>

## Constraints
- <repo, runtime, API, compatibility, design-system, data-format, or safety constraints>

## Acceptance criteria
- <observable result — each one must be verifiable by a test, command, log, or review>

## Assumptions
- <explicit assumption or default the user has not confirmed>

## Open questions
- <anything unresolved — must be empty or explicitly accepted before `plan`>
```

## design.md

```markdown
# Design: <title>

Upstream spec: <run-dir path>/spec.md

## Overview
<how the system technically works, in prose — ArjanCodes step 3>

## Data model
<tables/entities/fields, or the core data structures. Mermaid erDiagram when useful>

## Module & component design
<modules, key classes/functions, responsibilities, and the patterns chosen. Mermaid
flowchart/classDiagram for the relationships. Apply: functions over classes; small and
simple units; separate creation from use; abstraction at dependency boundaries>

## Key algorithms & libraries
<the algorithms that matter and third-party dependencies, each with a one-line "why">

## Edge cases & failure modes
<specific cases the system must handle correctly, e.g. network error, empty input,
concurrent write — each with intended behavior>

## Ripple effects (ArjanCodes step 6)
- Documentation to update:
- Users/systems to notify:
- External systems affected:

## Broader context (ArjanCodes step 7)
- Limitations of this design:
- Possible future extensions:
- Moonshots: <"it would be really cool if…" — 1–3 items>
```

## decisions.md

```markdown
# Design decisions

<one entry per significant decision — append-only across re-runs>

## D1: <decision title>
- Decision: <what was chosen>
- Alternatives considered: <and why rejected>
- Consequences: <what this makes easier/harder>
```

## plan.md

```markdown
# Plan: <title>

Upstream design: <run-dir path>/design.md

## Risk factors (ArjanCodes step 5 — identified first)
- <risk> → mitigation/alternative route: <…>

## Checkpoints
<small, independently verifiable slices. Front-load the risky ones. Each checkpoint:>

### Checkpoint 1: <name>
- Does: <what this slice delivers>
- Touches: <files/modules>
- Verify: <the command/check that proves this slice — must exist in
  verification-plan.md>

### Checkpoint 2: …

## Phases (optional — for large scope)
<use when the plan exceeds ~6 checkpoints or spans multiple subsystems; a flat
checkpoint list stays the default for small work. Phases group checkpoints into
milestones (ArjanCodes step 5); front-load the riskiest phase. Each phase boundary is
a verify point and a legitimate re-plan point — later phases may be revised based on
what earlier phases revealed.>

### Phase A: <name>
- Goal: <one line — what is true when this phase is done>
- Checkpoints: 1–3
- Boundary: run `verify` before entering Phase B

### Phase B: …

## Definition of Done
- Required: <absolutely required parts>
- Optional-later: <parts that can be done at a later stage>

## Migration / one-off scripts
<needed migration scripts, or "none">
```

## checklist.md

```markdown
# Checklist: <title>

<one line per checkpoint; `build` ticks these as evidence lands — never pre-tick.
When the plan uses phases, group the lines under phase headings:>

## Phase A: <name>
- [ ] 1. <checkpoint name> — verify: <check>
- [ ] 2. <checkpoint name> — verify: <check>
- [ ] Phase boundary — run `verify`

## Phase B: <name>
- [ ] 3. <checkpoint name> — verify: <check>
```

## verification-plan.md

```markdown
# Verification plan

<written by `plan`, BEFORE any code exists. Executed by `verify`.>

## Criteria
- <what "good" means, per acceptance criterion from spec.md>

## Checks
<the smallest sufficient set. Prefer existing project checks over invented ones.>
- `<command or manual check>` proves <claim / acceptance criterion>

## External signals
- <logs, screenshots, deployed endpoint, generated output — or "none available">

## Risk-based expansion
- Run <broader suite> if <condition, e.g. shared behavior or public API touched>

## Cannot be verified
- <checks that are impossible locally, and why — declared up front, not discovered late>
```

## build-log.md

```markdown
# Build log

<appended by `build` after each checkpoint — never rewritten>

## <UTC timestamp> — Checkpoint <n>: <name>
- Approval: <quote of the user's approving message>
- Changed: <files, one line each>
- Verified: <check run + result>
- Notes: <deviations from plan, discoveries, scope changes flagged>
```

## verify-report.md

```markdown
# Verify report

Plan under test: <run-dir path>/verification-plan.md

## Passed
- `<check>` — <evidence: exit code, output line, artifact>

## Failed
- `<check>` — <evidence + failing checkpoint + suggested route back to build>

## Not run
- `<check>` — <honest reason>

## Coverage gaps
<acceptance criteria with no covering check — from vibe-test-designer when present>

## Verdict
<pass | fail — fail if any acceptance criterion is unverified or failing>
```

## review.md

```markdown
# Review

Scope reviewed: <diff range / files>
Upstream artifacts: <spec/design/plan paths used as ground truth>

## Correctness
<bugs, logic errors, unhandled edge cases — reference findings.json entries>

## Surgical-diff audit
<changed lines that do NOT trace to the spec/checkpoints; unrelated "improvements";
orphans left behind>

## Simplicity
<over-engineering per the Karpathy rules: speculative abstraction, unrequested
configurability, 200-lines-that-could-be-50>

## Security
<from vibe-security-auditor when present — input validation, secrets, injection,
dependency pins, unsafe defaults>

## Conventions & docs
<style consistency with the repo; docs the diff should have updated>

## Verdict
<counts by severity; blockers listed first with remediation>
```

## env-report.md

```markdown
# Agent environment report

## Current state
<what exists: CLAUDE.md/AGENTS.md, README, docs, package scripts, conventions — and
what context the agent repeatedly has to rediscover>

## Proposed changes
<the full diff/content proposed — CLAUDE.md sections, knowledge-base files. NOT yet
written to the repo>

## Applied
<empty until the user gives explicit written approval; then list what was written>
```

## CLAUDE.md template

Proposed by `env` for repos that lack agent instructions. Keep it short enough to be
read every session.

```markdown
# Agent Instructions

## Project Context
- Purpose:
- Main entrypoints:
- Important boundaries:

## How To Work Here
- Read existing patterns before changing code.
- Prefer small, reviewable changes.
- Define verification before implementation.
- Report commands run and checks skipped.

## Common Commands
- Install:
- Test:
- Typecheck:
- Lint:
- Build:

## Guardrails
- Always: <actions the agent may perform autonomously>
- Ask first: <useful but needs approval>
- Never: <must not happen in this workspace>

## Approval Boundary
Do not edit files, install packages, run migrations, commit, deploy, delete data,
or perform other mutating work without explicit written approval.
```

Optional knowledge base (only when the repo has enough recurring context to justify
it — prefer a few durable files over many tiny ones):

```text
agent-knowledge/
  decisions.md
  architecture.md
  commands.md
  workflows.md
  examples.md
```

## summary.md

Written by every run-dir mode, last. Keep it terse — it is what the next mode (and the
human) reads first.

```markdown
# Run summary

- Mode: <mode>
- Target: <repo path> (greenfield | existing)
- Scope: <one line>
- Upstream run consumed: <run-dir name or "none">
- Sub-agents used: <names or "none available">
- Artifacts: <list>
- Findings: <counts by severity, verify/review only>
- Next: <next pipeline mode + its approval boundary>
```
