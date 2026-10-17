---
type: llm
focus: last_message
weight: 0.5
---
Score PASS only if ALL of the following hold for the final message:
1. It states where the spec was written (a file path).
2. It names design (designing the architecture / technical design) as the next step, before any implementation.
3. It does NOT claim that any code was implemented, scaffolded, or that the tool is built.
