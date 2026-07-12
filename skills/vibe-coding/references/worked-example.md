# Worked example — `photodedupe`, greenfield

End-to-end walkthrough of the full pipeline on a small greenfield project, plus the
existing-codebase variant at the end. Artifact excerpts are abbreviated; structure
follows `templates.md` exactly.

**Scenario.** User: *"Let's build a CLI tool that finds duplicate photos in a folder
tree and moves them to a review directory."* Target `~/code/photodedupe` is an empty
directory → greenfield.

## 1. define

```bash
python3 scripts/new_run_dir.py --repo ~/code/photodedupe --mode define --force
# → …/.claude/vibe-reports/2026-07-09T14-02-10Z    (pointer `latest` now → this dir)
```

(`--force` because a greenfield dir has no root markers yet.)

Probe runs once (`probe_subagents.py`) → all five present (skill-adjacent). Greenfield
→ interview leads. High-impact questions asked (not a survey): what counts as a
duplicate (exact bytes vs. same image re-encoded)? destructive or reversible? size of
libraries in play? The user answers: perceptual duplicates matter, must be reversible,
~50k photos.

`spec.md` (excerpt):

```markdown
# Spec: photodedupe CLI

## Goal
Find duplicate photos across a folder tree and move all-but-one of each duplicate
group into a review directory, reversibly, for ~50k-photo libraries.

## Scope
- In (MVP): exact-duplicate detection (content hash); recursive scan; move + manifest
  for undo; dry-run mode; JPEG/PNG/HEIC.
- Out: perceptual (near-duplicate) matching — deferred: needs tuning UX; GUI; cloud.

## Acceptance criteria
- Running on a tree with known duplicates moves all-but-one of each group to the
  review dir and writes a manifest that `--undo` restores exactly.
- `--dry-run` reports the same groups and moves nothing.
- A corrupt/unreadable file is skipped with a warning, never crashes the run.
- 50k files complete in < 5 min on a laptop (hashing parallelized).

## Open questions
- none (perceptual matching explicitly deferred to Out)
```

Summary ends: *next mode `design` (read-only)*.

## 2. design

New run dir `2026-07-09T14-20-45Z` (pointer advances). Upstream `spec.md` loaded from
`latest`. Python target → `python-stack.md` applies (UV, Black 119, pytest).

`design.md` (excerpt): data model = `PhotoRecord(path, size, sha256)` + duplicate
groups keyed by hash; modules `scan.py` (walk + filter), `hashing.py` (parallel
sha256), `grouping.py`, `mover.py` (move + JSON manifest + undo), `cli.py` (argparse,
thin). Functions over classes throughout; `mover` takes the manifest writer as an
argument (creation separated from use). Edge cases: corrupt file → warn + skip;
collision-paranoia → byte-compare before move; review dir inside scanned tree →
excluded from scan. Ripple effects: README, manifest format documented. Limitations:
exact-match only; moonshot: perceptual hash behind the same grouping interface.

**vibe-architect dispatched** (contract: `repo_path`, `run_dir`, `artifact_paths` =
spec + design, `task` = critique). Returns:

```json
{
  "agent": "vibe-architect",
  "findings": [
    {
      "category": "simplicity",
      "severity": "risk",
      "file": "design.md",
      "message": "Plugin registry for hash algorithms is speculative — spec has exactly one algorithm in scope",
      "remediation": "Drop the registry; a plain function parameter covers the moonshot later"
    }
  ]
}
```

Design revised (registry dropped); decision recorded in `decisions.md` (D2: plain
callable over registry — consequence: perceptual hash later = one new function).

## 3. plan

New run dir `2026-07-09T14-41-03Z`. Risk factors first: HEIC decoding on stock
laptops (mitigation: hash raw bytes, no decode needed for exact match — kills the
risk); 50k-file performance (front-loaded as checkpoint 2 with a synthetic-tree
benchmark).

Checkpoints (each with `verify:`): 1. scaffold + scan/filter (`uv run pytest
tests/test_scan.py`); 2. parallel hashing + benchmark (`uv run python bench.py
--files 50000` < 5 min); 3. grouping + dry-run report; 4. mover + manifest + undo
round-trip test; 5. CLI wiring + README.

**vibe-test-designer dispatched** → drafts `verification-plan.md`: each acceptance
criterion mapped to a check; discovers there are no existing project checks
(greenfield) so proposes the pytest layout; declares "5-min on a real laptop" only
approximable in CI (external signal: local run evidence). `checklist.md` written
unticked. Summary ends: *next mode is `build` — mutates the repo, requires explicit
written approval per checkpoint scope.*

## 4. build — in place on `latest`

No new run dir; pointer frozen at the plan dir. Fail-fast check passes
(`latest/plan.md` + `checklist.md` exist).

Approval gate: *"Plan has 5 checkpoints; I propose starting with checkpoint 1
(scaffold + scan). Approve?"* — User: **"Yes, implement checkpoint 1."** (Recorded
verbatim in `build-log.md`. A bare "ok" would have been pushed back on.)

Checkpoint loop: implement smallest slice → inspect own diff (surgical: nothing
outside `Touches`) → run the checkpoint's check → tick `checklist.md` → append
`build-log.md`:

```markdown
## 2026-07-09T15:02:44Z — Checkpoint 1: scaffold + scan
- Approval: "Yes, implement checkpoint 1."
- Changed: pyproject.toml, src/photodedupe/{__init__,scan}.py, tests/test_scan.py
- Verified: `uv run pytest tests/test_scan.py` → 4 passed
- Notes: none
```

Mid-build re-confirmation example: checkpoint 2 needs `pillow` for the HEIC filter —
a new dependency mutates `pyproject.toml` beyond the plan's `Touches`, so build stops
and asks; user approves; noted in the log. Checkpoints 2–5 proceed the same way.

## 5. verify

New run dir `2026-07-09T16-30-12Z` — **pointer advances away from the plan dir**; to
re-enter build afterwards, pass `…/2026-07-09T14-41-03Z` explicitly.

Runs `verification-plan.md`: full pytest suite, undo round-trip, dry-run check, bench.
One failure: corrupt-file warning goes to stdout, criterion says warning (stderr
implied by CLI conventions — vibe-test-designer flags it as `tests`/`risk`).
`verify-report.md`: Passed 5 / Failed 1 / Not run 0; verdict **fail** (criterion
unmet). `findings.json` gets the failure with `"checkpoint": "3"`. Summary: *route
back to `build` for a fix checkpoint.* A one-line fix checkpoint is approved, built,
and a re-run `verify` (new run dir) passes.

## 6. review

New run dir. Diff scope from `build-log.md` file lists. **vibe-code-reviewer** +
**vibe-security-auditor** dispatched; merged per `schemas.md` (dedupe file+line+
category, severity-sorted). Sample outcome: `simplicity`/`advisory` — bench script
left a debug flag; `security`/`risk` — manifest written world-readable in a shared
tmp dir (remediation: `0600`). No blockers → exit 0. `review.md` lists both with
remediations; summary suggests `env` to persist the project's commands into CLAUDE.md.

---

## Existing-codebase variant

Same pipeline, three behavioral differences:

1. **Grounding leads, interview follows.** `define` inspects entrypoints, routes,
   schemas, tests first; questions are about intent only ("narrow fix or durable
   abstraction?"). The spec gains an *interface impact* note (ArjanCodes step 2) for
   how the feature changes existing UX/structure.
2. **Design must fit repo idiom.** vibe-architect (or the inline fallback) treats
   divergence from existing layering/conventions as `design-drift`, and
   `python-stack.md` defaults yield to whatever the repo already uses (e.g. Poetry).
3. **Ripple effects are real.** Step 6 lists actual docs, consumers, and external
   systems; `plan` adds regression checkpoints (risk-based expansion: run the full
   suite because shared behavior is touched); `review`'s surgical-diff audit has
   teeth — pre-existing dead code stays untouched.

No `--force` needed: the repo has root markers.
