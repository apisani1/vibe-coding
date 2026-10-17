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
6. It shows the public API as a caller would use it (a minimal usage example for BOTH the decorator and the context manager), and the acceptance criteria specifically cover: max attempts, exponential backoff with jitter (bounded/testable, e.g. via injectable clock or random), per-exception retry predicates, the overall deadline, and having zero runtime dependencies.
Do NOT consider whether implementation code was written — a separate grader checks that.
