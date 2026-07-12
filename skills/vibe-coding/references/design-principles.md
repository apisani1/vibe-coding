# Design principles

The content layer of vibe-coding: what each mode thinks about (ArjanCodes 7 steps),
and how the agent behaves while building (Karpathy LLM guidelines + agentic loop
invariants). Load this file when writing spec/design/plan content or enforcing build
behavior.

## Contents

1. [The ArjanCodes 7 steps](#the-arjancodes-7-steps) — mapped to modes
2. [Karpathy behavioral guidelines](#karpathy-behavioral-guidelines) — enforced in `build`, audited in `review`
3. [Agentic-loop invariants](#agentic-loop-invariants) — cross-cutting, all modes

---

## The ArjanCodes 7 steps

A framework for thinking through a design before and while building. Each step feeds a
specific mode; the bullet questions are the interview/checklist material for that mode.

### Step 1 — Define what you're building (→ `define`)

- What is the software application or feature?
- Who's it intended for?
- What problem does it solve?
- How is it going to work?
- What are the main concepts involved and how are they related?

Working notes:
- **Design and prototype in parallel.** Don't perfect the design before implementing —
  a crude prototype surfaces technical limitations that reshape the design, and
  analyzing the domain reshapes the technology choices. (This is why the pipeline is
  soft: it's normal to bounce between `define`/`design` and a spike.)
- **Distill the model.** Removing concepts simplifies the design and focuses it on the
  core. The best refactoring is deleting code.
- **Zoom out, then zoom in.** First think as broadly as possible about what the
  software entails; then decide what to build first, what can be delayed, and what
  order reduces complexity and speeds up testing.
- **Define the MVP.** The minimum work necessary to test whether the thing is useful.
  This becomes the `In scope` section of the spec.

### Step 2 — Design the user experience (→ `define`)

- What are the main user stories — happy flows **and** alternative flows?
- For a feature in an existing app: what impact does it have on the overall structure
  of the interface (menus, navigation, organization)?
- UI mockups or wireframes clarify flows when relevant (text sketches are fine).

Working notes:
- **You're designing for someone else.** What you design must make sense to the user —
  sometimes an extra concept clarifies the system; sometimes the most generic solution
  is the wrong one.
- **Check that users actually need it before building it.** Generic, powerful, unused
  features are the most expensive failure mode. UI is among the most time-consuming
  parts of software (docs, communication, future bugs) — spend it only on what users
  will use.

### Step 3 — Understand the technical needs (→ `design`)

- What technical details do developers need to know?
- New database tables? What fields?
- How will it technically work? Important algorithms or libraries?
- What's the overall design? Which classes/modules? Which patterns model the concepts?
- What third-party software is needed?

Code-level guidelines (these are also the vibe-architect's review criteria):

- **a. Use functions over classes.** Functional code is typically simpler. Introduce a
  class when you're passing too many arguments around or need an object representation
  of data.
- **b. Keep things small and simple.** Modules, functions, methods, number of instance
  variables — small units are easier to read and test.
- **c. Separate creating the thing from using the thing.** Don't create an object and
  immediately call methods on it; create it outside and pass it in — easier to test.
- **d. Use abstraction.** ABCs/Protocols in Python, Traits in Rust — they remove
  dependencies and reduce the chance of breakage.
- Describe the specific **edge cases** the system must handle correctly (e.g. what
  happens on a network error).
- Use **Mermaid** for diagrams — text-based, renders on GitHub/VS Code.

### Step 4 — Implement testing and security measures (→ `plan` for the testing half, `verify`/`review` for execution, security half owned by vibe-security-auditor)

- Are there specific coverage goals for unit tests?
- What kinds of tests are needed (unit, regression, end-to-end…)?
- Feature in an existing app: potential side-effects on other areas?
- What security checks must be in place before shipping?
- Does the feature change the security posture? Is a security audit needed pre-ship?

Working notes:
- **Testing is a mindset, not just bug-finding.** Designing code that's easy to test
  produces code that handles edge cases by default. Design interfaces that nudge users
  into the happy flow.
- **Lean on the type system.** An Enum instead of a string argument makes the invalid
  role unrepresentable — the type checker handles the edge case, not runtime code.
- **Settle on a coding standard, don't be fancy.** An automatic formatter and best
  practices carry most of the weight (see `python-stack.md`).
- **Don't chase 100% coverage.** Write tests assuming you'll change things; focus on a
  basic version of the feature you can evaluate. Assume every line might be thrown
  away — don't get attached.

### Step 5 — Plan the work (→ `plan`)

- What are the steps, and roughly how big is each?
- What are the developmental milestones and in what order?
- Any migration scripts needed?
- What are the main risk factors, and what are the alternative routes if something
  isn't feasible?
- What is absolutely required vs. optional-later — the **Definition of Done**?

Working notes:
- **Find the risk factors first.** The riskiest part is usually the unfamiliar
  integration, not the UI around it. More risk factors → reserve more time for nasty
  surprises. Front-load risky checkpoints so infeasibility surfaces early.

### Step 6 — Identify ripple effects (→ `design`)

- What needs to happen outside designing and implementing the feature?
- What documentation needs updating?
- Do existing users need to be told something?
- Are other external systems affected (payment provider, email, sales systems)?

Working note: the processes *around* software — releasing, communicating, making sure
customers can use it — take real time. Think about them during design so they don't
appear at the last minute.

### Step 7 — Understand the broader context (→ `design`)

- What are the limitations of the current design?
- What are possible future extensions?
- Other considerations — budget, timeline, organizational?

Working notes:
- **Include a few "moonshots"** ("it would be really cool if it could also do X") —
  they open the mindset and sometimes an epiphany during development makes one cheap.
- **Write down the limitations.** They're the immediate starting point for the next
  round of changes.

Meta-note from the guide: understanding the problem is the phase most developers skip,
and it matters more than design patterns. That is why `define` and `design` come before
any code and produce reviewable artifacts.

---

## Karpathy behavioral guidelines

Behavioral rules that reduce common LLM coding mistakes. They bias toward caution over
speed — for trivial tasks, use judgment. Enforced during `build`; `review` audits the
diff against them (rules 2 and 3 map directly to the `simplicity` finding category and
the surgical-diff audit).

### 1. Think before coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity first

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: **every changed line should trace directly to the spec/checkpoint.**

### 4. Goal-driven execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

Every checkpoint in `plan.md` carries a `verify:` line for exactly this reason. Strong
success criteria let the agent loop independently; weak criteria ("make it work")
require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites
due to overcomplication, and clarifying questions come before implementation rather
than after mistakes.

---

## Agentic-loop invariants

Cross-cutting rules from the Karpathy agentic-engineering loop. Every mode obeys them.

1. **Ground in repo truth before asking questions.** Inspect entrypoints, patterns,
   tests, package scripts, and docs first. Never ask the user for facts discoverable
   from the workspace. Ask only for product intent and missing context.
2. **Interview for intent, not for a survey.** A few high-impact questions. If the user
   already gave a decision-complete plan, summarize it in one short paragraph and move
   on — do not re-interview.
3. **Keep scope reviewable.** Prefer the smallest useful slice over a broad rewrite.
   Name assumptions explicitly in the artifact.
4. **Verification before implementation.** The checks that will prove the work are
   written down (`verification-plan.md`) before any code exists. If verification is
   impossible or incomplete, say so before starting — not after.
5. **Explicit written approval before mutating work.** Edits, installs, migrations,
   commits, deploys, deletes. Approval must be clear, written, and action-specific:
   "Implement the fix you described" counts; "ok" / "sure" / "sounds good" does not,
   unless it clearly authorizes the concrete mutation. Read-only exploration is always
   allowed.
6. **Work in checkpoints.** Smallest coherent slice → inspect the diff → run the
   slice's checks → report → next slice. Update the user when direction, scope, or
   risk changes.
7. **Finish with evidence.** Report what changed, what was verified, what failed, what
   was not run, and follow-up risks. Never claim completion without running the agreed
   checks or clearly naming the gap. Do not trust confident output — collect evidence.
