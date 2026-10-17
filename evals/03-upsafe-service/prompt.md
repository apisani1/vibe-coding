---
max_turns: 30
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep, Write, "Bash(python3:*)", "Bash(ls:*)", "Bash(mkdir:*)"]
runs: 3
---
Build a file-upload HTTP service. It accepts multipart uploads, validates file type against an allow-list and enforces a max size, defends against path traversal, stores files to a quarantine directory under randomized names, and serves them back through a download-by-token endpoint. Treat security as a first-class concern throughout. Python, UV. The target is the current (empty) directory. Write the spec first.
