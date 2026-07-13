<!-- Example vibe-coding preference profile. Copy this whole directory to
     ~/.claude/vibe-coding/profile/ and edit to taste. It is consulted ONLY for bare
     greenfield builds (empty repos); scaffolded/existing repos use their own config. -->
---
# Structured tool choices — the agent synthesizes pyproject.toml and dev config from these.
package_manager: uv
python_version: "3.12"
formatter: black
line_length: 119
import_sorter: isort
linter: [flake8, pylint]
type_checker: mypy
test_framework: pytest
src_layout: true
license: MIT
editor: vscode
precommit: true
---

# Style philosophy

Prose the agent reads and applies with judgment when writing code for a bare-greenfield
project. Keep it short and principled — this is guidance, not a rulebook.

- **Functions over classes.** Reach for a class only when there is real state to
  encapsulate or a protocol to implement; otherwise a plain function is clearer.
- **Small, pure, composable units.** Separate construction from use — pass collaborators
  in rather than constructing them inside the function that uses them.
- **Explicit over implicit.** Type-annotate public functions; prefer keyword arguments
  for anything non-obvious; no bare `except:`.
- **Tests are first-class.** Every public behavior has a `pytest` test; name tests for the
  behavior they pin, not the function they call.
- **Docstrings explain *why*, not *what*.** The code says what; the docstring says the
  intent and the tradeoff.
