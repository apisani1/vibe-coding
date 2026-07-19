# vibe-coding — test kickoff prompts

Ready-to-paste `/vibe` prompts to exercise every branch of the skill. **Run each in a
separate session.** For each: run the one-time **Setup** in your shell, paste the
**Prompt** into a fresh Claude Code session, then use **Watch for** to judge success.

Targets use `~/code/...`; change to taste. Greenfield targets should be empty dirs — the
skill creates its run dir with `--force`.

Note: the examples in this folder are the results of running the prompts above and a single round of bug review using OpenAI Codex and a few fixes implemented by Claude Code.

---

## 1. Small bare-greenfield CLI — full happy path
*Exercises: greenfield detection, `define → design → plan → build → verify → review`, the fast end-to-end artifact set.*

**Setup:** `mkdir -p ~/code/mdtoc`

**Prompt:**
```
/vibe define ~/code/mdtoc

Build a CLI that injects and updates a Markdown table of contents. It scans a
.md file and writes a linked TOC between `<!-- toc -->` and `<!-- /toc -->`
markers. Requirements: idempotent (re-running produces no diff), a `--check`
mode that exits non-zero when the TOC is stale, and `--max-depth`. Python, UV,
pytest. Write the spec first, then take me through design and plan.
```

**Watch for:** greenfield interview (a few high-impact questions, not a survey); a run
dir under `~/code/mdtoc/.claude/vibe-reports/`; `spec.md` with observable acceptance
criteria and In/Out scope; each mode names the next; no source written during
define/design/plan.

---

## 2. Multi-subsystem greenfield — phase grouping
*Exercises: `plan` grouping checkpoints into phases with verify boundaries; risk-first ordering.*

**Setup:** `mkdir -p ~/code/shorturl`

**Prompt:**
```
/vibe define ~/code/shorturl

Build a URL shortener as a single deployable service with four parts: a SQLite
persistence layer, an HTTP API (create short code, redirect, per-code stats), a
CLI admin (list / expire / delete codes), and click analytics with expiry. This
spans several subsystems — when we get to planning, group the work into phases
with a verify boundary at the end of each, and front-load the riskiest phase.
Python, UV. Write the spec first.
```

**Watch for:** when you reach `plan`, a `## Phases` structure (not a flat checklist);
each phase has a one-line goal and an end-of-phase verify; the riskiest subsystem is
sequenced first; `build` re-confirms at each phase boundary.

---

## 3. Security-sensitive service — vibe-security-auditor
*Exercises: the security sub-agent, `security`/`dependency` findings, verify/review security spot-checks.*

**Setup:** `mkdir -p ~/code/upsafe`

**Prompt:**
```
/vibe define ~/code/upsafe

Build a file-upload HTTP service. It accepts multipart uploads, validates file
type against an allow-list and enforces a max size, defends against path
traversal, stores files to a quarantine directory under randomized names, and
serves them back through a download-by-token endpoint. Treat security as a
first-class concern throughout. Python, UV. Write the spec first.
```

**Watch for:** the interview surfaces threat-model questions; in `design`/`review` the
security auditor is dispatched (check the "Sub-agents used" line in the summary); findings
use `security`/`dependency` categories with concrete remediations.

---

## 4. Verification-heavy pure library — vibe-test-designer + verify
*Exercises: the test-designer sub-agent, acceptance-criterion → check mapping, a verify fail→fix→re-verify loop.*

**Setup:** `mkdir -p ~/code/rebackoff`

**Prompt:**
```
/vibe define ~/code/rebackoff

Build a small, dependency-free retry/backoff library: a `retry` decorator and a
matching context manager supporting max attempts, exponential backoff with
jitter, per-exception retry predicates, and an overall deadline. Strong testable
contracts and a comprehensive test suite are the whole point. Python, UV,
pytest. Write the spec first.
```

**Watch for:** in `plan`, the test-designer drafts `verification-plan.md` mapping each
acceptance criterion to a check; in `verify`, the full suite runs and any miss produces a
`tests`/`risk` finding routed back to a fix checkpoint, then a clean re-`verify`.

---

## 5. Existing-codebase feature — grounding-first, design-drift, ripple effects
*Exercises: the other detection branch — grounding in an existing repo, `design-drift` findings, regression checkpoints.*

**Setup:** pick one of your real repos (must have root markers like `.git`/`pyproject.toml`).

**Prompt** (replace the path and the feature):
```
/vibe define ~/code/<your-existing-repo>

Add <a --json output mode> to this existing project. Ground yourself in the
current structure, conventions, and tests first; call out any design drift and
ripple effects (docs, consumers, external systems) the change touches before
proposing it. Write the spec, including an interface-impact note. Then design
and plan it to fit the repo's existing idiom — don't introduce a new style.
```

**Watch for:** grounding leads and the interview asks intent only ("narrow fix or durable
abstraction?"); no `--force` needed (root markers exist); design respects existing
layering (divergence flagged as `design-drift`); `plan` adds regression checkpoints.

---

## 6. Autopilot (`--auto`) — the overseer, both outcomes
*Exercises: `vibe-overseer` as approver, the grant audit trail, and the hard-stop safety property. **Run these as two separate sessions.***

**6a — clean autonomous run (overseer approves every checkpoint).**
Setup: `mkdir -p ~/code/rebackoff-auto`
```
/vibe define ~/code/rebackoff-auto

Build the same dependency-free retry/backoff library as before (retry decorator
+ context manager, max attempts, exponential backoff with jitter, per-exception
predicates, deadline; pure stdlib, no third-party deps). Take it through spec,
design, and plan, then run the build autonomously with --auto and stop if
anything looks off.
```
**Watch for:** autopilot proceeds only because `vibe-overseer` is installed; the grant is
recorded in `state.json` (`build.auto` with the invocation quote); each checkpoint's
build-log says "auto-approved by vibe-overseer"; tight `Touches`, no new deps.

**6b — hard-stop run (overseer must reject).**
Setup: `mkdir -p ~/code/jsonfetch-auto`
```
/vibe define ~/code/jsonfetch-auto

Build a CLI that fetches a URL and pretty-prints the JSON response, with a
--timeout and colored output. Spec, design, and plan it, then run the build with
--auto. (I want to see how autopilot handles a checkpoint that needs a new
third-party dependency.)
```
**Watch for:** when a checkpoint needs a new dependency (e.g. an HTTP client) beyond the
plan's `Touches`, the overseer returns `verdict: reject`, the build **halts** instead of
continuing, and the stop report shows the reasons/findings and returns control to you. No
installs/pushes happen.

---

## 7. Scaffolded greenfield + headless CI
*Exercises: scaffolded-greenfield classification, and the `--ci --json` headless review path.*

**7a — scaffolded detection.** Setup: `generate-project generate ledgerkit` (creates
`~/AI/MyCode/ledgerkit` or your generator's default location — adjust the path below).
```
/vibe define ~/code/ledgerkit

I just scaffolded this repo with my project generator. Now build the real thing:
a CLI that converts CSV bank statements into double-entry ledger entries. Confirm
you detect that src/ is only scaffolder placeholder code (not a feature to
extend), and record the generated tooling (black/isort/flake8/mypy/pylint config,
Makefile targets, src layout) as spec constraints. Write the spec first.
```
**Watch for:** classified as **scaffolded greenfield** (new-product spec, not an extension
of the hello-world placeholder); `spec.md` Constraints capture the detected `[tool.*]`
tooling; placeholder `src/`/`tests/` left untouched.

**7b — headless CI review.** Run inside any repo you've already built above:
```
/vibe review --ci --json
```
**Watch for:** valid `findings.json` streamed to stdout (mode, scanned_at, subagents_used,
findings); every category from the allow-list; exit 0 clean / 1 on a blocker / 2 config
error; no interactive questions asked.

---


