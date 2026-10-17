---
type: llm
focus: last_message
---
The user gave a vague idea and the correct behavior is to interview for intent and STOP. Score PASS only if ALL hold:
1. The final message asks between 2 and 7 questions (count distinct top-level questions; more than 7 is a FAIL — that is a survey, not an interview).
2. The questions are specific to this idea, and at least two of them address: what counts as a "duplicate" (exact bytes vs. visually similar / resized / edited), what "clean up" means (delete vs. move vs. report, reversibility), or scale / storage location / file formats.
3. The message ends waiting for the user's answers — it does NOT present a finished spec, a design, an architecture, or any code.
