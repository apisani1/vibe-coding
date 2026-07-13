# Python stack defaults

Opt-in reference layer: apply when the target project is Python (`pyproject.toml`,
`setup.py`, or a dominant `*.py` tree). The core skill stays language-agnostic — this
file only supplies concrete tooling defaults so `design`/`plan`/`build`/`verify` don't
reinvent them per run. **Existing repos win:** if the target already has configured
tooling, use what's there; these defaults are for greenfield projects or gaps.

## Detecting which tools the user actually uses

A tool counts as **in use** only when the project *configures* it — being installed on
the PATH is not evidence (dev machines carry dozens of tools the project never runs).
Detection sources, in order of authority:

1. **`pyproject.toml` `[tool.*]` sections** — the primary mechanism. `[tool.black]`,
   `[tool.isort]`, `[tool.mypy]`, `[tool.pylint.*]`, `[tool.flake8]` (via the
   `flake8-pyproject` plugin), `[tool.ruff]`, `[tool.pytest.ini_options]`,
   `[tool.doc8]`… Each section present = that tool is part of the project's workflow.
2. **Dedicated config files** — `.flake8`, `setup.cfg` tool sections, `.pylintrc`,
   `mypy.ini`, `pytest.ini`, `tox.ini` tool sections, `.pre-commit-config.yaml`.
3. **Corroborating signals** — dev dependencies (`[dependency-groups]` /
   `[project.optional-dependencies]` / Poetry dev group), Makefile targets
   (`make lint`, `make pre-commit`), CI workflow steps.

Run and enforce **exactly the detected set** — all of them in `verify`, none that
aren't configured. Don't add new linters to an existing repo uninvited.

## Tooling defaults

Defaults apply only where detection finds nothing (bare greenfield). For scaffolded
repos, the generator's config **is** the detected set — honor it.

**Before falling back to the generic table below, check the user preference profile**
(`scripts/read_profile.py`, see SKILL.md § User preference profile and `schemas.md`). For
bare greenfield it supplies the user's own defaults — the values that `[tool.*]` detection
would otherwise find — so synthesize `pyproject.toml` from those (`package_manager`,
`formatter`/`line_length`, `linter`, `type_checker`, `test_framework`, …). The table below
is the fallback when no profile exists.

| Concern         | Default                              | Notes                                                        |
| --------------- | ------------------------------------- | ------------------------------------------------------------ |
| Package manager | **UV**                                | Check `pyproject.toml` first — older repos may use Poetry; follow the repo. |
| Formatting      | **Black**, line length **119**        | Via `pyproject.toml` `[tool.black] line-length = 119`.       |
| Imports         | **isort** (profile `black`)           | Same line length.                                            |
| Linting         | **flake8 / pylint / Ruff — if configured** (any or all) | Detected per the section above; run every one that is configured. No linter configured → Black+isort only. |
| Tests           | **pytest**                            | `tests/` mirroring `src/` layout.                            |
| Types           | mypy/pyright **if configured**        | Don't require; do run when present.                          |
| Pre-commit      | `make pre-commit` when a Makefile provides it | Run before proposing any commit.                     |

## Greenfield scaffold (proposed in `design`, created in `build`)

```
<project>/
├── pyproject.toml          # PEP 621, [tool.black], [tool.isort], deps via uv
├── src/<package>/
│   └── __init__.py
├── tests/
└── README.md
```

Commands (also the `Common Commands` block `env` proposes for CLAUDE.md):

```bash
uv init / uv add <dep>        # deps  (uv add --dev for dev deps)
uv sync                       # install
uv run pytest                 # test
uv run black . && uv run isort .   # format
make pre-commit               # when the repo provides it — run before commits
```

## Mode hooks

- **design**: name concrete third-party libraries with a one-line "why"; prefer the
  standard library when it's within ~20% of the convenience.
- **plan**: each checkpoint's `verify:` should be a `uv run …` command wherever
  possible — runnable, not prose.
- **build**: match repo style over these defaults on conflict. New deps require the
  user's approval before `uv add` (it mutates `pyproject.toml` + lockfile).
- **verify**: run in order — existing test suite, formatter check
  (`black --check`, `isort --check-only`), then **every configured linter and type
  checker** (flake8, pylint, ruff, mypy/pyright — per the detection section above).
  Report tool output verbatim in evidence.
- **review**: conventions section checks against this table only for greenfield code;
  for existing repos, the repo's own idiom is the standard (surgical-changes rule).
