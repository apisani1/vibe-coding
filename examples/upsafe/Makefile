.PHONY: format lint typecheck test pre-commit run

format:
	uv run isort src tests
	uv run black src tests

lint:
	uv run flake8 src
	uv run pylint src

typecheck:
	uv run mypy src

test:
	uv run pytest

# Formats then lints + type-checks — the gate to run before committing.
pre-commit: format lint typecheck
	@echo "pre-commit: all checks passed"

run:
	uv run python -m upsafe
