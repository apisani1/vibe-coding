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
6. The acceptance criteria include checkable security cases, each with an expected observable result (status code or behavior): a disallowed file type is rejected, an over-size upload is rejected, a path-traversal filename (e.g. ../../etc/passwd) cannot escape the quarantine directory, stored filenames are randomized (not user-controlled), and an invalid/unknown token is rejected on download.
Do NOT consider whether implementation code was written — a separate grader checks that.
