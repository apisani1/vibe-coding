---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, "Bash(python3:*)", "Bash(ls:*)", "Bash(mkdir:*)"]
runs: 3
---
Build a small, dependency-free retry/backoff library: a `retry` decorator and a matching context manager supporting max attempts, exponential backoff with jitter, per-exception retry predicates, and an overall deadline. Strong testable contracts and a comprehensive test suite are the whole point. Python, UV, pytest. The target is the current (empty) directory. Write the spec first.
