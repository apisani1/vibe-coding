# Agent environment report

## Current state
- **Before:** no `CLAUDE.md`/`AGENTS.md`, no git repository. The project was fully built
  and reviewed via the vibe pipeline (artifacts under `.claude/vibe-reports/`), but had
  no durable, session-loaded agent instructions and no version control.
- Existing knowledge the agent would otherwise rediscover each session: the core/IO
  separation, the load-bearing invariants (idempotence fixed point, whitespace contract,
  exit codes, zero-runtime-deps), the UV command set, and the "replicate not import
  Python-Markdown" decision. These are captured in spec/design/decisions but not in a
  single short file read every session.

## Proposed changes
- Add `CLAUDE.md` at the repo root (see `../../../CLAUDE.md`) distilling: project purpose
  and entrypoints, the 4-module architecture, the non-breakable invariants, the common
  UV commands, and always/ask-first/never guardrails — short enough to read every
  session.
- No `agent-knowledge/` base proposed: the design/decisions artifacts already hold the
  deep context, and a few durable pointers in `CLAUDE.md` are sufficient for a tool this
  size. Adding tiny knowledge files would be over-provisioning.
- No new skill proposed: no repeated multi-step workflow beyond the standard
  test/format/run loop, which the commands block covers.

## Applied
- Approval: "Implement the the advisory fix and set up env/git" (explicit written
  approval to set up env).
- Written: `CLAUDE.md` at repo root (project context, architecture, invariants, common
  commands, guardrails, approval boundary).
- Also set up git in the same request (see git section below / build history): `git init`
  on `main`, added `.gitignore` (Python/UV: `.venv/`, `__pycache__/`, build/test caches),
  and an initial commit of the full project + vibe artifacts.
