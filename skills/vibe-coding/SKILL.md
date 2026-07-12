---
name: vibe-coding
description: |
  Manage the full lifecycle of building software libraries and applications with AI
  agents ("vibe coding"): research, agent-environment setup, spec definition, design,
  planning, checkpointed implementation — including approved autonomous/autopilot
  runs — verification, and review. Activate whenever the user wants to build, design,
  spec, plan, verify, review, or autonomously drive the building of software — phrases
  like "vibe code", "let's build <thing>", "design this app/library", "write a spec
  for", "plan this feature", "start a new project", "set up my agent environment",
  "build this autonomously", "run the build and stop if something looks off",
  "verify this build", "review what we built", or "/vibe <mode>" (any mode or flag
  such as --auto). Use it for both greenfield projects and features in existing
  codebases, even if the user doesn't say "vibe coding" explicitly — any non-trivial
  request to create software from an idea, or to take an idea through
  spec → design → plan → build, belongs here.
---

# vibe-coding

Production-grade orchestrator for developing software with AI agents. It turns a vague
idea into a tight **spec**, a reviewed **design**, a phased **plan** with verification
defined up front, a checkpointed **build**, and evidence-based **verify**/**review**
passes — with explicit human approval gates before anything mutates the repo.

The skill merges three sources, each operating at a different layer:

- **ArjanCodes 7-step design guide** — *what each mode thinks about* (define → UX →
  technical needs → testing & security → plan → ripple effects → broader context).
- **Karpathy agentic-engineering loop** — *how each mode behaves* (ground in repo
  truth, interview, tight spec, verification before implementation, explicit approval,
  small checkpoints, evidence-based completion).
- **Karpathy LLM guidelines** — *behavioral rules during build* (think before coding,
  simplicity first, surgical changes, goal-driven execution).

Deep versions live in `references/design-principles.md`. The skill is language-agnostic;
a Python-aware layer (`references/python-stack.md`) applies when the target is Python.

## Inputs

| Param    | Purpose                                                        | Default                                                                 |
| -------- | -------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `mode`   | `ask \| env \| define \| design \| plan \| build \| verify \| review` | Infer from the request; ask if ambiguous. |
| `target` | Path to the target repo/project root                           | Current working directory.                                              |
| `scope`  | What is being built (project, library, feature description)    | Interview the user.                                                     |
| `--ci`   | Headless mode (`verify` / `review` only)                       | Off                                                                     |
| `--json` | Emit `findings.json` payload to stdout                         | Off                                                                     |
| `--auto` | Autopilot: vibe-overseer assumes the approver role (`build` only; see Approval boundaries) | Off                                          |

In `--ci` mode, also accept env vars `VIBE_MODE`, `VIBE_TARGET`.

When invoked via the slash command `/vibe <mode> [target] [--ci] [--json] [--auto]`,
parse positional args in that order. The command file is a thin wrapper that activates
this skill.

**Greenfield vs. existing codebase** — auto-detect by looking at what the source tree
*contains*, not just whether repo markers exist. Project generators (cookiecutter,
`uv init`, `npm create`, `cargo new`, in-house scaffolders) produce `.git`,
`pyproject.toml`/`package.json`, a Makefile, CI files, and a placeholder source tree —
that is still greenfield. Classify:

- **Bare greenfield** — no `.git`, no source tree. Interview leads; repo grounding is
  minimal.
- **Scaffolded greenfield** — repo markers exist but `src/` (or equivalent) holds only
  scaffolder placeholders: an `__init__.py` with just a version/docstring, a
  hello-world `main.py`/entry point, smoke tests that only import the package. No
  domain logic anywhere. Interview leads, but **honor the generated infrastructure**
  (tooling config, layout, Makefile targets) as constraints — it encodes the user's
  conventions (see `references/python-stack.md` for tool detection).
- **Existing codebase** — the source tree contains real domain code. Ground every mode
  in the existing patterns first and treat the work as a feature/extension.

## Modes

Each mode produces a defined artifact set. Detailed runbooks live in
`references/modes.md` — **read that file before executing any mode**.

| Mode     | Action                                                                                                          | Artifacts (in run dir)                             | Sub-agents                                |
| -------- | ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------ |
| `ask`    | Research/investigate/answer only. No run dir, no artifacts, never mutates.                                       | none                                                | none                                       |
| `env`    | Audit + set up the agent environment (CLAUDE.md / knowledge base). Diff first, write after approval.             | `env-report.md`                                     | none                                       |
| `define` | Interview → spec (ArjanCodes 1–2). Goal, audience, user stories, MVP scope, acceptance criteria.                 | `spec.md`                                           | none                                       |
| `design` | Technical design (ArjanCodes 3, 6, 7). Data model, modules, Mermaid, edge cases, ripple effects, limitations.    | `design.md`, `decisions.md`                         | vibe-architect                             |
| `plan`   | Phased plan (ArjanCodes 4–5). Checkpoints + **verification defined before any code**.                            | `plan.md`, `checklist.md`, `verification-plan.md`   | vibe-test-designer                         |
| `build`  | Execute `latest/plan.md` in checkpoints with human approval. **Operates in place** on `latest`; no new run dir.  | Updates `checklist.md`, appends `build-log.md`      | vibe-overseer (`--auto` only)              |
| `verify` | Run `verification-plan.md`; report Passed / Failed / Not-run honestly.                                           | `verify-report.md`, `findings.json`                 | vibe-test-designer, vibe-security-auditor  |
| `review` | Code review of what was built: correctness, surgical-diff audit, simplicity, security.                           | `review.md`, `findings.json`                        | vibe-code-reviewer, vibe-security-auditor  |

All run-dir modes also write `summary.md` and `state.json` (mode, inputs, upstream run
consumed — schema in `references/schemas.md`).

**Pipeline.** The soft pipeline is `define → design → plan → build → verify → review`.
Each mode loads its upstream artifact from `latest` (or an explicit run-dir path the
user provides) and, if it is missing, offers to run the missing upstream mode first
(e.g. `design` with no spec offers to run `define`). `ask` and `env` are entry points
usable at any time. `verify` failures route back to `build` as the next checkpoint;
`review` blockers route back to `plan` or `build`. Large plans group checkpoints into
**phases** (milestones); `verify` runs at each phase boundary, and later phases may be
re-planned from what earlier phases revealed.

### Run-directory semantics

All artifacts live under `.claude/vibe-reports/` in the target repo. Modes that produce
a fresh run (`env`, `define`, `design`, `plan`, `verify`, `review`) create a new
`<UTC-timestamp>/` directory (`YYYY-MM-DDTHH-MM-SSZ`) and update the pointer file
`.claude/vibe-reports/latest` to contain that directory's name. Use a pointer file,
**not a symlink** — Windows.

`build` is the exception: it operates **in place** on the directory that `latest`
currently points to, so the plan being executed is never orphaned by pointer
advancement. It does not advance `latest`. If `latest/plan.md` or `latest/checklist.md`
is missing, `build` fails fast. `ask` writes nothing anywhere.

Implication: once `verify` runs after `build`, `latest` advances away from the plan
directory. To resume `build` against the original plan, pass the explicit run-dir path.
Mention this in user-facing help when relevant.

Use `scripts/new_run_dir.py --repo <target> --mode <mode>` to create the run directory
and update the pointer atomically (it refuses `ask` and `build`). Use
`scripts/probe_subagents.py --repo <target>` to check which specialist sub-agents are
installed.

## Approval boundaries (safety-critical)

- `ask`, `define`, `design`, `plan`, `verify`, `review` are **read-only with respect to
  repo code**: they write only inside their own run dir. `verify` and `review` may run
  the project's existing checks (tests, linters, builds); ask first before any check
  that mutates state (migrations, deploys, installs).
- `env` proposes a CLAUDE.md / knowledge-base diff and writes it **only after explicit
  written approval**.
- `build` requires **explicit, written, action-specific approval** before its first
  mutation, and re-confirms when scope, direction, or risk changes mid-build. Vague
  replies like "ok", "sure", or "sounds good" are **not** approval — acceptable approval
  clearly authorizes the concrete action ("Yes, implement checkpoint 1 as planned").
- If the user asks for implementation while a read-only mode is active, explain what
  would change and ask for written approval before switching to `build`.
- **Autopilot (`--auto`)** is the one sanctioned exception, and it moves the gate
  rather than removing it: the user's `--auto` invocation is recorded verbatim as the
  explicit, written, coarse-grained approval for the run, and **vibe-overseer** —
  which must be installed; the skill refuses autopilot when the probe doesn't find it,
  and there is **no inline fallback for the approver role, ever** — reviews each
  checkpoint's diff and evidence against the plan before approving the next. Any
  rejection, blocker finding, plan deviation, or `max_checkpoints` cap stops the run
  and returns control to the human. Even under `--auto`: `env` writes, installs,
  deploys, pushes, migrations, and anything outside the target repo still require
  direct human approval. Runbook: `references/modes.md § Autopilot`.

## Sub-agent orchestration

The five specialists (`vibe-architect`, `vibe-test-designer`, `vibe-code-reviewer`,
`vibe-security-auditor`, `vibe-overseer`) are **enhancements, not prerequisites** —
with one exception: `vibe-overseer` is *required* for `--auto` (an approver cannot be
inlined). The skill is the orchestrator and lightweight fallback; sub-agents are deep
specialists.

1. At the start of every run, call `scripts/probe_subagents.py` and record availability
   in `summary.md` under "Sub-agents used".
2. For each mode with an owning sub-agent (table above): present → dispatch via the Task
   tool using the **`invoke_name`** the probe reports (bare name for user/project
   installs; `vibe-coding:<agent>` when installed as a plugin — never hardcode the bare
   name), and skip the inline checks for that category; absent → run the inline fallback
   checklist in `references/modes.md`. The same `invoke_name` rule applies to
   `vibe-overseer` under `--auto`.
3. Invocation contract (pass in the agent message): `repo_path`, `run_dir`,
   `artifact_paths`, `scope_glob` (default `**/*`), `task`.
4. Each sub-agent returns a fenced ```json block **first** (contract in
   `references/schemas.md`), then a human-readable narrative. Extract the block, merge
   its `findings` into the run's `findings.json`, dedupe by `file`+`line`+`category`,
   and prepend `"agent": "<name>"` per finding for traceability.

**Per-agent model configuration.** The target repo may carry
`.claude/vibe-coding.local.md` with YAML frontmatter mapping agents to models
(`models: {vibe-architect: opus, vibe-test-designer: haiku}`) plus
`auto_max_checkpoints`. The probe script reads it and reports a `model` per specialist.
Apply the requested model in the dispatch where the harness supports a model override;
where it doesn't, record the request in `summary.md` and tell the user to set the
agent file's `model:` frontmatter instead — never edit agent files silently. Agent
files ship with `model: inherit`, so the session model is the default everywhere.

## findings.json

Canonical machine-readable output of `verify` and `review` (full schema and merge rules:
`references/schemas.md`):

```json
{
  "mode": "verify | review",
  "scanned_at": "<UTC ISO-8601>",
  "subagents_used": ["vibe-code-reviewer"],
  "findings": [
    {
      "category": "correctness | tests | simplicity | security | design-drift | docs | dependency | advisory",
      "severity": "blocker | risk | advisory",
      "file": "src/x.py",
      "line": 42,
      "checkpoint": "3.2",
      "message": "…",
      "remediation": "…",
      "agent": "vibe-code-reviewer"
    }
  ]
}
```

**Severity grading:** `blocker` — acceptance criteria unmet, broken behavior, or an
exploitable-now security hole; `risk` — likely to surface latent issues; `advisory` —
opportunity, not a problem. Categories are a strict allow-list — never invent new ones;
pick the closest and explain the nuance in `message`.

In `--ci`: any `blocker` → exit 1; clean or `risk`/`advisory` only → exit 0; config
error → exit 2.

## Workflow

Every invocation follows the same shape:

1. **Parse inputs.** Resolve `mode`, `target`, `scope`. Interactive: ask only for what's
   missing. `--ci`: exit 2 if anything required is unresolved.
2. **Ground in repo truth before asking questions.** Inspect entrypoints, existing
   patterns, tests, package scripts, docs. Never ask the user for facts discoverable
   from the workspace.
3. **Probe sub-agents** (`scripts/probe_subagents.py`); record availability.
4. **Create the run directory** (`scripts/new_run_dir.py`) — except for `ask` (writes
   nothing) and `build` (operates in place on `latest`).
5. **Act per mode.** Read the runbook in `references/modes.md`. Load the mode's
   templates from `references/templates.md`.
6. **Emit artifacts** to the run dir. Pretty-print `findings.json` (2-space indent).
7. **Print a terse end-of-run summary**: mode, target, run directory, key artifacts,
   counts by severity (verify/review), sub-agents used, and — always — **the next mode
   in the pipeline and its approval boundary**. With `--json`, also stream
   `findings.json` to stdout.

## Behavioral principles (enforced in `build`, audited in `review`)

Summary — the deep version with rationale is `references/design-principles.md`:

1. **Think before coding.** State assumptions; present competing interpretations
   instead of picking silently; push back when a simpler approach exists.
2. **Simplicity first.** Minimum code that solves the problem. No speculative features,
   abstractions for single-use code, or error handling for impossible scenarios.
3. **Surgical changes.** Every changed line traces to the spec. Don't "improve"
   adjacent code; remove only orphans your own changes created.
4. **Goal-driven execution.** Every checkpoint has a verifiable success criterion
   defined before the code is written; loop until verified, report honestly.

## CI integration

The skill ships no CI YAML. Recipe-only guidance lives in `references/ci-recipe.md`.
Summary:

```bash
claude -p "/vibe review --ci --json" > findings.json
jq -e '[.findings[] | select(.severity == "blocker")] | length == 0' findings.json
```

Or trust the exit code (0 clean, 1 blockers, 2 config error).

## Recipe examples

- "Let's build a CLI tool that dedupes my photo library" → `define` (greenfield)
- "Write a spec for adding OAuth to this API" → `define` (existing codebase)
- "Design it" (after a define run) → `design`, loading `latest/spec.md`
- "Plan the work" → `plan`, loading `latest/design.md`
- "Start building" / "implement checkpoint 1" → `build` (approval gate first)
- "Did it work?" / "verify the build" → `verify`
- "Review what we built" → `review`
- "Why does the login test flake?" → `ask` (research only, no artifacts)
- "Set up CLAUDE.md for this repo" → `env`
- Slash: `/vibe define`, `/vibe plan ~/code/myproj`, `/vibe review --ci --json`
  (when installed as a plugin the command is namespaced: `/vibe-coding:vibe …`)

## Tone & non-goals

**Tone.** Senior-staff-engineer level: practical, operational, concise. Avoid generic
advice, superficial checklists, and vague recommendations. Prefer a few high-impact
interview questions over long surveys.

**Non-goals.** This skill is **not**:

- an autonomous end-to-end code generator — every mutation happens inside the
  checkpointed, approval-gated `build` loop;
- a project-management tool (no tickets, estimates beyond plan phasing, or scheduling);
- a CI system (it emits findings and exit codes; the pipeline is the user's);
- a substitute for the project's own test suite (it defines and runs checks; it does
  not chase 100% coverage — see `references/design-principles.md`).

## Reference index

| File                                | When to read                                                        |
| ----------------------------------- | -------------------------------------------------------------------- |
| `references/modes.md`               | Before running any mode — per-mode runbook + inline fallbacks        |
| `references/design-principles.md`   | Writing spec/design/plan content; enforcing build behavior           |
| `references/templates.md`           | Emitting any artifact — canonical templates                          |
| `references/schemas.md`             | Building or merging `findings.json` / `state.json`; sub-agent contract |
| `references/python-stack.md`        | Target is a Python project — tooling defaults                        |
| `references/worked-example.md`      | End-to-end walkthrough (greenfield + existing-codebase variant)      |
| `references/ci-recipe.md`           | The user asks about CI integration                                   |
