---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, "Bash(python3:*)", "Bash(ls:*)", "Bash(mkdir:*)"]
runs: 3
---
Build a CLI that injects and updates a Markdown table of contents. It scans a .md file and writes a linked TOC between `<!-- toc -->` and `<!-- /toc -->` markers. Requirements: idempotent (re-running produces no diff), a `--check` mode that exits non-zero when the TOC is stale, and `--max-depth`. Python, UV, pytest. The target is the current (empty) directory. Write the spec first.
