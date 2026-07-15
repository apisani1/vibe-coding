# Checklist: mdtoc — Markdown TOC injector

Ticked by `build` as evidence lands — never pre-ticked.

- [x] 1. Scaffold + slug fidelity — verify: `uv run pytest -q tests/mdtoc/test_slug.py`
- [x] 2. Heading scanner — verify: `uv run pytest -q tests/mdtoc/test_headings.py`
- [x] 3. Markers + TOC builder — verify: `uv run pytest -q tests/mdtoc/test_document.py -k "markers or build_toc or max_depth or h1 or duplicate or fence"`
- [x] 4. render orchestration — idempotence + equivalence — verify: `uv run pytest -q tests/mdtoc/test_document.py tests/mdtoc/test_render_idempotence.py`
- [x] 5. CLI + exit codes + packaging — verify: `uv run pytest -q tests/mdtoc/test_cli.py && uv run mdtoc --help && uv run python -m mdtoc --help`
- [x] 6. README + green suite + format gate — verify: `uv run pytest -q && uv run black --check . && uv run isort --check-only .`
