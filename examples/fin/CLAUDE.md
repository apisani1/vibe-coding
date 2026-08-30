# CLAUDE.md — working in this repository

@./planning

Read `planning/README.md` first; it is short and it lists the five rules that are invisible
from the code depending on them. The full contract — spec, design, decisions, plan,
verification plan — is in that directory.

## Commands

```bash
make check     # backend pytest + mypy --strict + flake8 + black/isort + pylint;
               # frontend vitest + tsc + eslint. Run before every commit.
make e2e       # 21 Playwright specs against the real container (needs Docker)
make up        # start the app; make down stops it and keeps the volume
```

## Conventions

- **Python** — `uv`, Python 3.12, black/isort at 119 columns, `mypy --strict` over `src`,
  pylint at 10.00. Tests are excluded from strict typing, not from linting.
- **TypeScript** — no `any`, no non-null assertion outside tests, `@/` imports.
- **Comments explain *why*.** This codebase is dense with them because most of its decisions
  are non-obvious and several were paid for with a defect. Do not strip them for brevity.
- **`.env` is gitignored and must stay that way.** `.env.example` is the committed template.

## Non-negotiable behaviours

Breaking any of these is a defect even if every test still passes — several of them *did*
pass while broken, which is why they are written down.

1. **`services/` never imports a web framework.** The HTTP layer and the assistant both call
   the same functions, and that is what makes D5 true rather than aspirational.
2. **Validation belongs in the service, not only in the request model.** The assistant does
   not construct request models.
3. **`/api/*` always answers JSON** — including unknown paths and the bare `/api`. The static
   export is mounted last, and there is an explicit JSON 404 in front of it. A frontend that
   receives HTML from an API path fails in a way nobody can read.
4. **Money moves in exactly one place**: `services/portfolio.execute_trade`, inside one
   `BEGIN IMMEDIATE` transaction that reads the price once.
5. **A refused action is reported as refused**, with the server's sentence, in both the REST
   error and the chat transcript.

## Testing standard

A test that has never been seen to fail is a comment. When you add a guard, mutate the thing
it guards and watch it die — this project has six recorded cases of a mutation that did not
mutate, or a check that could not fail, and every one of them was found by *running* the
battery rather than reading it.

Fixtures must be states the backend can actually produce: `total_value == cash_balance +
positions_value`, and positions consistent with the value they claim. A fixture that cannot
occur is a check that cannot fail.
