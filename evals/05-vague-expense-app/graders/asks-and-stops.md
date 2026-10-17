---
type: llm
focus: last_message
---
The user gave a vague idea and the correct behavior is to interview for intent before building anything, then STOP. Score PASS only if ALL hold:
1. The final message asks between 2 and 7 questions (count distinct top-level questions; more than 7 is a FAIL — that is a survey, not an interview).
2. The questions are specific to this idea, and at least two of them address: who uses it (single person vs. household members), platform/form factor (CLI, web, mobile, spreadsheet), what must be tracked or reported (categories, budgets, shared costs, imports from bank), or what the minimal first version is.
3. The message ends waiting for the user's answers. It does NOT commit to a tech stack or start building: no code, no file layout, and no claim that anything was built. A clearly labelled suggestion (e.g. "my suggested starting point, if you agree: …") that the user is asked to confirm or change is fine and must NOT cause a FAIL.
