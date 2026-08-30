# FinAlly — the checks that would otherwise be a CI file.
#
# There is no CI in this repo, so `make check` is what re-runs the earlier
# phases' gates while the later ones are built. It is also the documented
# pre-commit step, which is why it must stay fast and must not need Docker: a
# target that takes minutes stops being run, and a check nobody runs is a
# comment.

.DEFAULT_GOAL := help
.PHONY: help check backend-check frontend-check e2e build up down clean

help:  ## Show this help
	@grep -E '^[a-z0-9-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

check: backend-check frontend-check  ## Everything that runs without Docker

backend-check:  ## Backend: tests, strict types, lint, format
	cd backend && uv run pytest -q
	cd backend && uv run mypy --strict src
	cd backend && uv run flake8
	cd backend && uv run black --check .
	cd backend && uv run isort --check-only .
	cd backend && uv run pylint src

frontend-check:  ## Frontend: tests, types, lint
	cd frontend && npm run test
	cd frontend && npm run typecheck
	cd frontend && npm run lint

e2e:  ## End-to-end: 21 Playwright specs against the real container
	# `--build` is load-bearing, not tidiness. `docker compose up` builds only
	# when the image is MISSING, so once `finally:e2e` exists this target drives
	# whatever was built last and reports green on it. On 2026-08-20 that gave a
	# passing 21-spec run against an image four days old, carrying neither CP18
	# nor CP19 — `grep -c TrustedHostMiddleware` inside it answered 0. Nothing in
	# the harness noticed; it was caught because one startup log line was absent
	# from the container output. Three recorded "green" E2E runs were produced
	# this way, and one of them is retracted in build-log.md.
	#
	# The cost is a cache-hit rebuild on every run, which is seconds. The
	# alternative cost is a suite that cannot fail.
	#
	# The teardown runs whether or not the suite passed. On its own recipe line
	# a red run aborts make and leaves the stack up — no data risk, since this
	# stack has no named volume, but containers nobody asked for.
	cd test && ( docker compose -f docker-compose.test.yml up --build \
		--abort-on-container-exit --exit-code-from playwright; \
		status=$$?; docker compose -f docker-compose.test.yml down; exit $$status )
	@echo "Screenshots: test/screenshots/"

build:  ## Build the production image
	docker build -t finally:latest .

up:  ## Start the app (idempotent)
	./scripts/start_mac.sh

down:  ## Stop the app. Never removes the volume.
	./scripts/stop_mac.sh

clean:  ## Remove build outputs and caches. Never touches the finally-data volume.
	rm -rf frontend/.next frontend/out frontend/tsconfig.tsbuildinfo
	rm -rf backend/src/finally_app/static
	rm -rf test/test-results test/playwright-report
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "Left alone: node_modules, .venv, and the finally-data volume (your portfolio)."
