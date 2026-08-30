---
auto_max_checkpoints: 19
---

# vibe-coding local config — FinAlly

`auto_max_checkpoints` raised from the default 10 to 19 so an `--auto` run can attempt the
full plan (`.claude/vibe-reports/2026-08-13T23-18-51Z/plan.md`, checkpoints 0–17 plus 4b)
in a single pass. Authorized by the user on 2026-08-13.

Raising the cap does not weaken any other stop condition: vibe-overseer still reviews every
checkpoint, and the run still ends immediately on a rejection, a blocker-severity finding,
a plan-is-wrong condition, or any action needing out-of-repo mutation.
