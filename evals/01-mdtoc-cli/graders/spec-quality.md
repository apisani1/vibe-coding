---
type: llm
focus: trace
---
Find the specification document the agent wrote to a file (any path or filename — see Write tool calls in the trace). A spec that appears only in chat does NOT count. Score PASS only if ALL of the following hold for that spec:
1. A complete specification document was written to a file.
2. It has a stated Goal (the user outcome / problem solved, not just a restatement of the task).
3. It has an explicit MVP scope split into In and Out, and each Out item has a short reason.
4. It has an Acceptance criteria list in which EVERY criterion is observable — checkable by a specific command, test, exit code, or file comparison. Any vague criterion ("works well", "is fast", "user-friendly", "robust") is a FAIL.
5. It lists assumptions explicitly.
6. The acceptance criteria specifically cover: (a) re-running on an up-to-date file produces no diff, (b) `--check` exits non-zero when the TOC is stale and zero when current, (c) `--max-depth` limits included heading levels.
Do NOT consider whether implementation code was written — a separate grader checks that.
