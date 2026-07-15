# mdtoc

Inject and update a linked **table of contents** in a Markdown file. `mdtoc` scans a
`.md` file's headings and rewrites the block between `<!-- toc -->` and `<!-- /toc -->`
with an up-to-date, correctly linked TOC.

It is **idempotent** — re-running on an already-current file produces no change — so it
is safe in an editor-save hook, and its `--check` mode turns that into a CI gate that
fails when a committed TOC goes stale.

## Install

```bash
uv sync
```

## Usage

Add the two markers where you want the TOC, then run the tool:

```markdown
# My Document

<!-- toc -->
<!-- /toc -->

## First Section
...
```

```bash
uv run mdtoc README.md            # fill/update the TOC in place
uv run mdtoc --check README.md    # exit non-zero if the TOC is stale (writes nothing)
uv run mdtoc --max-depth 2 doc.md # only include headings up to level 2
python -m mdtoc doc.md            # module entrypoint, equivalent to the console script
```

The tool edits the file **in place** and only ever rewrites the text between the
markers; everything outside them is left untouched.

## Behavior

- **Idempotent.** `mdtoc` defines "current" as *"running the tool would change nothing"*.
  The writer and `--check` share that single predicate, so `--check` can never disagree
  with what a write would produce.
- **Leading H1 skipped.** A single leading `#` title is treated as the document title and
  omitted from the TOC; headings are listed from the next level down.
- **Duplicate headings** get distinct anchors (`heading`, `heading_1`, `heading_2`, …).
- **Code fences are respected.** Headings — and marker lines — inside ` ``` ` / `~~~`
  fenced code blocks are ignored, so a document may show the marker syntax without being
  managed. (An unterminated fence causes later headings to be omitted.)

## Anchor style

Slugs follow the **Python-Markdown `toc` extension** algorithm (as used by MkDocs and
Sphinx-style toolchains): Unicode-normalized, punctuation stripped, lowercased,
whitespace hyphenated, and collisions disambiguated with `_1`/`_2` suffixes. `mdtoc` has
**no runtime dependencies** — the algorithm is replicated, not imported.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| `0`  | Success, or (`--check`) the TOC is already current |
| `1`  | (`--check` only) the TOC is stale |
| `2`  | Usage / IO error, or missing / malformed markers |

## Notes & limitations

- ATX headings (`#`…`######`) only; Setext (underline) headings are not detected.
- When `mdtoc` rewrites a file, its output uses LF line endings with a single trailing
  newline. It does not rewrite a file just to change line endings: if the TOC is already
  current the file is left byte-for-byte untouched, so an existing CRLF file keeps its
  endings. Use a dedicated formatter if you need unconditional LF normalization.
- Inline Markdown in a heading (e.g. `**bold**`) is shown verbatim in the link text.

## Development

```bash
uv run pytest                                 # test suite
uv run black --check . && uv run isort --check-only .   # format gate
uv run flake8 src tests                       # lint (max line length 119)
uv run pylint src/mdtoc                        # lint (src only)
uv run mypy src/mdtoc                          # type-check (strict)
```

The optional slug cross-check test (`markdown` installed as a dev dependency) asserts
`mdtoc`'s slugs match Python-Markdown exactly; it is skipped when `markdown` is absent.
