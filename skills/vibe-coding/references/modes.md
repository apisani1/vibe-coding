# Mode runbooks

Per-mode execution guides. Read the runbook for the requested mode before acting.
Templates for every artifact: `templates.md`. Content guidance (ArjanCodes steps,
Karpathy rules): `design-principles.md`. Schemas and sub-agent contract: `schemas.md`.

Common to all modes:

- Ground in repo truth first; ask the user only what the workspace cannot answer.
- Probe sub-agents once per run (`scripts/probe_subagents.py --repo <target>`); record
  the result in `summary.md`. Dispatch when present, fall back inline when absent.
- Run-dir modes (`env`, `define`, `design`, `plan`, `verify`, `review`): create the dir
  via `scripts/new_run_dir.py --repo <target> --mode <mode>`, write the mode artifacts
  plus `summary.md` and `state.json`, and end with a terse summary naming the next mode
  and its approval boundary.
- Upstream chaining: resolve the upstream artifact from
  `.claude/vibe-reports/latest` unless the user passed an explicit run-dir path. If
  it's missing, **offer to run the missing upstream mode first** — don't silently
  fabricate an upstream.

## Contents

- [ask](#ask) · [env](#env) · [define](#define) · [design](#design) · [plan](#plan) ·
  [build](#build) · [verify](#verify) · [review](#review)

---

## ask

Research, investigation, debugging, and direct answers. **No run dir. No artifacts.
Never mutates.**

1. Investigate with non-mutating tools only: read files, search code, inspect configs,
   review logs, run safe read-only diagnostics.
2. Answer the actual question directly — what is happening, why, and the evidence.
   Cite specific files, commands, logs, or observations. Do not default to a long
   implementation plan.
3. State the recommended next action(s) in plain language; call out uncertainty and
   what further investigation would reduce it.
4. If the next step would mutate anything, end by making the approval boundary
   explicit. If the user asks for implementation mid-`ask`, explain what would change
   and ask for written approval — vague "ok"/"sure" is not approval. After approval,
   do only the approved action, scope tight.

`ask` is also the right mode for "should we use X or Y?" questions during any other
mode — answer, then return to the pipeline.

## env

Set up the workshop the agent operates inside: durable context, reusable knowledge,
explicit safety rules. Artifacts: `env-report.md`, `summary.md`, `state.json`.
Repo writes **only after explicit written approval**.

1. **Audit.** Look for CLAUDE.md/AGENTS.md, README, architecture docs, package
   scripts, test commands, project conventions. Identify context the agent repeatedly
   has to rediscover. Record in `env-report.md § Current state`.
2. **Propose.** Draft durable agent instructions from the CLAUDE.md template in
   `templates.md` — repo purpose, boundaries, common commands, validation
   expectations, and always/ask-first/never guardrails. Keep it short enough to read
   every session. Propose a knowledge base (`agent-knowledge/`) only when recurring
   context justifies it — a few durable files over many tiny ones. Propose a new skill
   only for a workflow the user demonstrably repeats.
3. **Show the diff.** Write the full proposed content into
   `env-report.md § Proposed changes`. Present it and stop.
4. **Apply only after explicit written approval.** Then record what was written in
   `§ Applied`. Any instructions this mode creates must themselves state the approval
   boundary (the template already does).

## define

ArjanCodes steps 1–2 + the spec interview. Artifact: `spec.md` (+ `summary.md`,
`state.json`). Read-only wrt repo code.

1. **Ground.** Classify the target (SKILL.md § Greenfield vs. existing codebase) by
   inspecting the source tree's *content*, not just repo markers:
   - Bare greenfield (no `.git`, no source tree): skip to the interview.
   - Scaffolded greenfield (markers exist, but `src/` holds only generator
     placeholders — a version-only `__init__.py`, a hello-world entry point, smoke
     tests that only import the package): interview leads, but record the generated
     infrastructure (tool config in `pyproject.toml`, Makefile targets, layout) as
     spec constraints — the scaffolder encodes the user's conventions.
   - Existing codebase (real domain code present): inspect entrypoints, routes,
     schemas, tests, docs first so interview questions are informed, not generic.
2. **Interview for intent.** Identify the real goal — the outcome or decision the work
   enables, not the task wording. High-impact questions, not a survey:
   - "What decision or user outcome should this enable?"
   - "Who is this for, and what problem does it solve for them?"
   - "What are the main user stories — including the unhappy paths?"
   - "What should stay unchanged?" / "What would make this unacceptable?"
   - "Should this be a narrow fix, a durable abstraction, or a broader redesign?"
   If the user already supplied a decision-complete description, confirm it in one
   short summary and proceed — do not re-interview.
3. **Zoom out, then in.** Map the main concepts and relationships; then cut to the
   MVP: the minimum that tests whether the thing is useful. Distill — remove concepts
   that aren't core.
4. **Write `spec.md`** per the template: goal, concepts, user stories (happy +
   alternative flows), In/Out scope, constraints, acceptance criteria (each one
   observable), assumptions, open questions.
5. **Quality gate before emitting:** every acceptance criterion is verifiable by a
   test/command/log/review; scope is small enough to review; assumptions are explicit.
   Open questions must be resolved or explicitly accepted by the user before `plan`.

Next: `design` (read-only).

## design

ArjanCodes steps 3, 6, 7. Artifacts: `design.md`, `decisions.md` (+ `summary.md`,
`state.json`). Read-only wrt repo code. Sub-agent: **vibe-architect**.

1. **Load upstream** `spec.md` (offer `define` if missing).
2. **Ground.** Existing codebase: catalogue the patterns, layers, and conventions the
   design must fit; a design that ignores the codebase's idiom is drift by
   construction. Greenfield: pick the simplest structure that satisfies the spec —
   and if the repo was scaffolded, design within the generated layout and tooling
   rather than proposing a competing structure.
3. **Draft `design.md`** per the template: overview, data model, module/component
   design with Mermaid, key algorithms & libraries (each with a why), edge cases &
   failure modes, ripple effects (step 6), broader context + limitations + moonshots
   (step 7). Apply the step-3 code guidelines: functions over classes; small simple
   units; separate creation from use; abstraction at dependency boundaries.
4. **Record decisions** in `decisions.md`: each significant choice with alternatives
   considered and consequences.
5. **Architect review.** If `vibe-architect` is present, dispatch it (contract in
   `schemas.md`) against `design.md` + `spec.md` + the codebase; fold its findings into
   the design (revise, or record disagreement in `decisions.md`). Inline fallback —
   self-review the draft against:
   - Does every design element trace to a spec requirement? (design-drift)
   - Is anything speculative — patterns, layers, or configurability the spec doesn't
     need? (simplicity; "would a senior engineer call this overcomplicated?")
   - Are the step-3 guidelines (a–d) respected?
   - Is every spec edge case owned by a component?
   - Are ripple effects and limitations honestly filled in, not boilerplate?

Next: `plan` (read-only).

## plan

ArjanCodes steps 4–5. Artifacts: `plan.md`, `checklist.md`, `verification-plan.md`
(+ `summary.md`, `state.json`). Read-only wrt repo code. Sub-agent:
**vibe-test-designer**.

1. **Load upstream** `design.md` (offer `design` if missing).
2. **Risk factors first.** Identify them before sequencing — the risky part is usually
   the unfamiliar integration. Give each a mitigation or alternative route. Front-load
   risky checkpoints so infeasibility surfaces early.
3. **Cut checkpoints.** Small, independently verifiable slices, each with: what it
   delivers, what it touches, and its `verify:` check. Avoid one-shot waterfall
   plans. Order for early testability. **For large scope** (more than ~6 checkpoints,
   or multiple subsystems), group checkpoints into **phases** (templates.md § Phases):
   front-load the riskiest phase; each phase boundary is a verify point and a
   legitimate re-plan point — commit only the current phase's checkpoints to detail,
   and expect later phases to be revised by what earlier ones reveal.
4. **Verification before implementation.** Write `verification-plan.md` now, before
   any code exists. If `vibe-test-designer` is present, dispatch it to draft the plan
   (it discovers existing project checks first). Inline fallback:
   - Translate each acceptance criterion into an observable check.
   - Discover what already exists: package scripts, test dirs, CI config, linters.
     Prefer existing checks over invented ones.
   - Choose the smallest sufficient set; add risk-based expansion conditions.
   - Declare up front what cannot be verified locally.
   - Don't chase 100% coverage — cover the acceptance criteria and the risks.
5. **Write `checklist.md`** — one line per checkpoint with its verify check, unticked.
6. **Definition of Done:** required vs optional-later, from the spec's MVP cut.

End-of-run summary must state: *next mode is `build`, which mutates the repo and
requires explicit written approval per checkpoint scope.*

## build

Execute the plan in checkpoints. **The only repo-mutating mode.** Operates **in place**
on the run dir `latest` points to — no new run dir, pointer frozen. Updates
`checklist.md`, appends `build-log.md`.

**Fail fast:** if `latest/plan.md` or `latest/checklist.md` is missing, stop and offer
to run `plan`. Never build without a plan.

1. **Load** `plan.md`, `checklist.md`, `verification-plan.md`, and the upstream
   spec/design for ground truth.
2. **Approval gate.** Before the first mutation, present the checkpoint(s) about to be
   built and get **explicit, written, action-specific approval** ("Yes, implement
   checkpoint 1" — not "ok"). The user may approve one checkpoint or a batch; record
   the quoted approval in `build-log.md`.
3. **Checkpoint loop**, for each approved checkpoint:
   a. Implement the smallest coherent slice, under the Karpathy rules
      (`design-principles.md`): state assumptions first; simplest code that passes the
      check; every changed line traces to the checkpoint; match existing style; remove
      only orphans you created.
   b. Inspect your own diff before declaring the slice done.
   c. Run the checkpoint's `verify:` check. Failing → fix within the slice; do not
      proceed on red.
   d. Tick the checkpoint in `checklist.md`; append the `build-log.md` entry
      (approval quote, files changed, check + result, notes).
   e. Report tersely to the user, then continue to the next approved checkpoint.
4. **Re-confirm** when direction, scope, or risk changes: a discovered constraint that
   invalidates the plan, a dependency to install, a file outside the plan's `Touches`
   list, anything destructive. Deviations are logged in `build-log.md § Notes`.
5. **Phase boundaries.** When the plan uses phases: at the end of each phase, stop,
   run (or propose) `verify` against the phase's criteria, and re-confirm approval
   before entering the next phase — a phase boundary is where re-planning is cheap.
   Under `--auto`, vibe-overseer performs this boundary review instead.
6. **Finish with evidence:** what changed, what was verified, what was not, follow-up
   risks — and name `verify` as the next mode.

If the plan proves wrong mid-build (not merely incomplete), stop and route back to
`plan` rather than improvising a new architecture inside `build`.

### Autopilot (`--auto`)

Opt-in autonomous build: the user's `--auto` invocation is the **explicit, written,
coarse-grained approval** for the run, and **vibe-overseer** assumes the per-checkpoint
approver role. Rules:

- **Precondition:** probe must find `vibe-overseer`. Absent → refuse autopilot and
  fall back to manual approval gates. There is **no inline fallback for the approver
  role — ever**: the skill must not approve its own work.
- **Grant recording:** write to `state.json` an `auto` object (`granted_at`,
  `grant_quote` — the user's command verbatim, `max_checkpoints` — default 10,
  overridable via `.claude/vibe-coding.local.md` `auto_max_checkpoints`).
- **Loop change:** after each checkpoint's verify evidence lands (step 3c), dispatch
  vibe-overseer with the checkpoint spec, the diff, and the evidence. `approve` →
  tick, log `Approval: auto-approved by vibe-overseer per --auto grant ("<grant
  quote>")`, continue. `reject` → **stop the run**, log the verdict and reasons,
  report to the human with the overseer's findings, and wait.
- **Hard stops** (end the run regardless of verdict): `max_checkpoints` reached; a
  blocker-severity finding from any source; the plan proves wrong (step 4's re-plan
  condition); any action needing out-of-repo mutation.
- **Unchanged boundaries:** `env` writes, installs, deploys, pushes, migrations, and
  anything outside the target repo still require direct human approval — `--auto`
  never covers them.

## verify

Execute `verification-plan.md`; report evidence honestly. Artifacts:
`verify-report.md`, `findings.json` (+ `summary.md`, `state.json`). New run dir
(`latest` advances — to re-enter `build` afterwards, pass the plan run-dir path
explicitly). Sub-agents: **vibe-test-designer** (coverage), **vibe-security-auditor**.

1. **Load** the verification plan from the build's run dir (`latest` at entry, or an
   explicit path). Missing → offer `plan`.
2. **Run the checks** in the plan. Read-only and existing project checks (tests, lint,
   typecheck, build) run freely; ask first before anything state-mutating
   (migrations, deploys, installs). Capture real evidence: exit codes, output lines,
   generated artifacts, screenshots/logs where relevant.
3. **Classify honestly:** Passed / Failed / Not run (with the honest reason). Never
   mark a skipped check as passed; never call the work complete with unverified
   acceptance criteria.
4. **Coverage gaps.** If `vibe-test-designer` is present, dispatch it to compare
   acceptance criteria against executed checks. Inline fallback: walk `spec.md`'s
   acceptance criteria and list any with no covering check as `tests` findings.
5. **Security spot-check.** If `vibe-security-auditor` is present, dispatch it over
   the built diff. (Inline fallback checklist: see [review](#review) step 4 — same
   list, scoped to the new code.)
6. **Emit** `verify-report.md` and `findings.json` (failures → `severity` per impact
   on acceptance criteria; unrunnable checks → `advisory` unless they guard a
   criterion, then `risk`). Verdict: fail if any acceptance criterion is failing or
   unverified.
7. Failures route back to `build` as the next checkpoint — say so in the summary.

CI: `--ci --json` → stream `findings.json` to stdout; exit 1 on blockers, 0 clean,
2 on config error (no plan found, target invalid).

## review

Independent quality pass over what was built. Artifacts: `review.md`, `findings.json`
(+ `summary.md`, `state.json`). New run dir. Read-only wrt repo code. Sub-agents:
**vibe-code-reviewer**, **vibe-security-auditor**.

1. **Establish scope.** The diff since the plan's baseline (from `build-log.md` file
   lists, or `git diff` against the pre-build ref) plus the upstream spec/design/plan
   as ground truth. No upstream artifacts → degrade gracefully: review the named
   files/diff against the repo's own conventions and say the trace-to-spec audit was
   skipped.
2. **Dispatch or fall back.**
   - `vibe-code-reviewer` present → dispatch with the diff scope. Inline fallback:
     - **Correctness first:** logic errors, unhandled edge cases from `design.md`,
       broken contracts, off-by-ones. (`correctness`)
     - **Surgical-diff audit:** every changed line traces to a checkpoint; flag
       unrelated "improvements", drive-by refactors, style churn, and orphans the
       build created. (`design-drift` / `simplicity`)
     - **Simplicity:** speculative abstraction, unrequested configurability,
       impossible-scenario error handling, 200-lines-that-could-be-50. (`simplicity`)
     - **Conventions & docs:** style consistency (Python: `python-stack.md`); docs the
       diff should have updated. (`docs`)
   - `vibe-security-auditor` present → dispatch. Inline fallback checklist:
     - Input validation at trust boundaries; injection surfaces (SQL/shell/path/
       template); secrets in code or logs; unsafe defaults (debug on, permissive
       CORS, world-writable); dependency pins for new deps. (`security` /
       `dependency`)
     - `blocker` **only** for exploitable-now issues; hardening ideas are `risk` or
       `advisory`.
3. **Merge findings** per `schemas.md` (dedupe `file`+`line`+`category`, `agent` field
   prepended). Write `review.md` with blockers first, each with remediation.
4. **Route:** blockers that reveal a wrong plan → `plan`; implementation-level
   blockers → `build`. Clean review → done; suggest `env` if the session surfaced
   reusable context worth persisting.

CI semantics identical to `verify`.
