# Spec: mdtoc — Markdown table-of-contents injector

## Goal
Give writers of long Markdown documents a **deterministic, one-command way to keep a
linked table of contents in sync with the document's headings.** A `mdtoc README.md`
run scans the file's headings and rewrites the block between `<!-- toc -->` and
`<!-- /toc -->` with an up-to-date, correctly linked TOC. The same file re-run produces
byte-for-byte no change (idempotent), so it is safe to wire into an editor-save hook or
a CI gate. A `--check` mode turns that idempotence into a build signal: it exits
non-zero when the committed TOC no longer matches the headings, so a stale TOC fails CI
instead of shipping. The value is trust — the TOC is never silently wrong, and keeping
it correct costs one command, not manual editing.

## Main concepts
- **Target document** — a single `.md` file passed on the command line.
- **TOC markers** — the literal HTML comments `<!-- toc -->` (open) and `<!-- /toc -->`
  (close). They delimit the managed region; everything between them is owned by the
  tool, everything outside is untouched.
- **Heading** — an ATX Markdown heading (`#`, `##`, …). Its *level* is the number of
  `#`; its *text* is the trimmed remainder.
- **Anchor / slug** — the URL fragment a heading links to, computed with the
  **Python-Markdown `toc`-extension algorithm** (see Constraints) so links resolve in
  MkDocs/Sphinx-style renderers.
- **TOC** — a nested bullet list of `[heading text](#slug)` links, indented by relative
  heading depth, written between the markers.
- **Staleness** — the condition where the current marker contents differ from what the
  tool *would* generate. `--check` reports it; a normal run repairs it.

```
target.md
  ├─ prose, headings ─────────────► scanned for headings
  └─ <!-- toc -->  …managed…  <!-- /toc -->  ◄── rewritten by tool
```

## Users & user stories
- As a **docs author**, I want to run `mdtoc README.md` after editing headings, so that
  the TOC reflects my current structure without hand-editing links.
- As a **docs author**, I want re-running the tool on an already-current file to change
  nothing, so that I can run it freely (e.g. on every save) without noise in my diffs.
- As a **CI maintainer**, I want `mdtoc --check docs/guide.md` to exit non-zero when the
  TOC is stale, so that a pull request with an out-of-date TOC fails the build.
- As a **docs author with a deep document**, I want `--max-depth 2` to list only H1–H2
  (or H2–H2 given the H1-skip rule), so that the TOC stays scannable instead of
  enumerating every sub-sub-section.
- *(Unhappy)* As a **user who forgot the markers**, when the file has no
  `<!-- toc -->`/`<!-- /toc -->` pair, I want the tool to refuse and exit non-zero with
  a clear message telling me to add them, so that it never rewrites a file I didn't
  opt in to manage.
- *(Unhappy)* As a **user who mistypes a path**, when the file doesn't exist or isn't
  readable, I want a clear error and a non-zero exit, so that scripts fail loudly.

## Scope
- **In (MVP):**
  - Single `.md` file path argument, edited **in place**.
  - Scan ATX headings (`#`…`######`); build a nested TOC of markdown links.
  - Python-Markdown `toc`-extension slug algorithm, including duplicate-slug
    disambiguation with `_1`, `_2`, … suffixes.
  - Skip the document's **leading H1 title** (a single H1 that is the first heading) —
    it is treated as the document title and excluded from the TOC. Headings are listed
    from the next level down.
  - Write the TOC between existing `<!-- toc -->` / `<!-- /toc -->` markers only.
  - **Idempotent** rewrite: a second run on the output yields no change.
  - `--check`: compute the would-be output, write nothing; exit `0` if the TOC is
    already current, non-zero if stale.
  - `--max-depth N`: cap the deepest heading level included.
  - Clear non-zero exits with stderr messages for: missing markers, unreadable/missing
    file, malformed marker pair (see Edge cases in design).
- **Out (deferred, with reasons):**
  - Multiple files / directory recursion / globbing — shell globbing + `xargs` covers
    batches; keeps the MVP a single-file transform. *(Deferred)*
  - Auto-inserting markers when absent — explicitly rejected for MVP; erroring is safer
    and was the chosen behavior. *(Deferred)*
  - GitHub-flavored slugs or other dialects — one slug algorithm (Python-Markdown) for
    MVP; a `--slug-style` flag can come later. *(Deferred)*
  - Setext headings (`===`/`---` underlines), Setext/HTML headings, headings inside
    fenced code blocks counted as headings — MVP handles ATX and must *ignore* headings
    inside fenced code blocks; other heading syntaxes are out. *(Partially deferred; see
    Assumptions.)*
  - `--min-depth`, custom marker strings, TOC title/heading text, stdin/stdout piping,
    config files. *(Deferred — not needed to prove the core value.)*
  - Non-`.md` inputs, front-matter awareness beyond leaving it untouched. *(Deferred.)*

## Constraints
- **Language/tooling:** Python 3, packaged and run with **UV**; tests in **pytest**.
  Formatting Black (line length 119) + isort (profile black) per user defaults; no
  linter is mandated for greenfield beyond that.
- **Slug algorithm (authoritative for MVP):** replicate Python-Markdown's `toc`
  extension default `slugify`:
  1. Unicode-normalize (NFKD) and drop non-ASCII (default `unicode=False` behavior).
  2. Remove every character that is not a word char, whitespace, or hyphen
     (`re.sub(r'[^\w\s-]', '', value)`), then `strip()` and `lower()`.
  3. Collapse runs of whitespace/separator into a single hyphen (`-`).
  4. **Disambiguate collisions** the way Python-Markdown does: the first occurrence of a
     slug is bare; each subsequent identical slug gets `_1`, `_2`, … (underscore +
     incrementing integer), matching `toc.py`'s `unique()` — **not** GitHub's `-1`.
- **Idempotence is a hard requirement:** the generated block (including its exact
  whitespace, indentation, trailing newline handling, and link ordering) must be a fixed
  point — running the tool on its own output changes nothing, byte for byte.
- **Marker fidelity:** the tool replaces only the text strictly between the marker
  lines; the marker comments themselves and all content outside them are preserved
  verbatim, including surrounding blank lines to the extent needed for idempotence
  (exact whitespace contract to be pinned in design).
- **Exit codes:** `0` = success / TOC already current; non-zero = stale (in `--check`)
  or any error. Distinct codes for "stale" vs "usage/IO error" to be fixed in design.
- **No network, no telemetry, no writes outside the target file** (and none at all in
  `--check`).

## Acceptance criteria
Each is observable via a test or a shell command:
1. **Injection:** given a file with empty markers and headings, a run fills the block
   with a nested link list; every list item is `[<heading text>](#<slug>)` and the slug
   matches the Python-Markdown algorithm. *(pytest on known input/output)*
2. **Idempotence:** running the tool twice on the same file leaves the file identical
   after the second run (`diff` of file-before-2nd-run vs file-after == empty). *(pytest
   + shell `diff`)*
3. **`--check` on current file:** exits `0` and does not modify the file (mtime/content
   unchanged). *(pytest capturing exit code + content)*
4. **`--check` on stale file:** after editing a heading without updating the TOC,
   `--check` exits non-zero and leaves the file unmodified. *(pytest)*
5. **`--max-depth`:** with `--max-depth 2`, no heading deeper than level 2 appears in the
   generated TOC; with a larger depth the deeper headings appear. *(pytest on a
   multi-level fixture)*
6. **Leading H1 skipped:** a document whose first heading is a single H1 does not list
   that H1 in the TOC; H2+ appear. *(pytest)*
7. **Duplicate headings:** two headings with identical text produce distinct anchors,
   the second suffixed `_1`, and both links are present. *(pytest)*
8. **Missing markers:** a file with no marker pair is left unmodified and the tool exits
   non-zero with a stderr message naming the missing markers. *(pytest)*
9. **Missing/unreadable file:** a nonexistent path exits non-zero with a clear stderr
   error and writes nothing. *(pytest)*
10. **Code fences ignored:** a `#`-prefixed line inside a fenced code block is not
    treated as a heading. *(pytest)*
11. **Packaging:** `uv run mdtoc --help` (or the agreed entrypoint) runs and prints
    usage; `uv run pytest` passes. *(command)*

## Assumptions
- **ATX headings only**, and headings inside fenced code blocks (```` ``` ```` or `~~~`)
  are ignored. Setext (underline) headings are out of MVP scope — flagged as an open
  question in case the user's real docs use them.
- **"Leading H1 title"** means: the first heading in the document is level 1 and there is
  exactly one such role. If the document has multiple H1s, only a *leading* one is
  treated as the title; subsequent H1s (if any) are ordinary entries. (Exact rule to be
  pinned in design; default: skip only the first heading iff it is H1.)
- The TOC's shallowest displayed level defines indentation depth 0; indentation is by
  **relative** heading level so a document starting at H2 isn't over-indented.
- `--max-depth` counts **absolute** Markdown heading level (e.g. `2` = include up to
  `##`), independent of the H1-skip rule.
- Default `--max-depth` when the flag is omitted is "all levels" (6).
- Line endings: MVP assumes LF; preserving CRLF is not guaranteed (open question).
- The CLI entrypoint/command name is `mdtoc` (package name to be settled in design).

## Open questions
- **Q1 — Setext headings:** do your real target documents ever use `===`/`---`
  underline headings? If yes, MVP scope must expand to detect them. *(Default if
  unanswered: ATX only, Setext out.)*
- **Q2 — Multiple H1s:** for documents with several H1 sections (not a single title),
  should *only the first* H1 be skipped, or every H1? *(Default: skip only the leading
  first-heading H1.)*
- **Q3 — Distinct exit codes:** do you want separate non-zero codes for "stale"
  (`--check`) vs "error" (bad usage / IO / missing markers), e.g. `1` vs `2`, or is any
  non-zero acceptable? *(Default: `1` = stale, `2` = usage/IO error, `0` = ok.)*
- **Q4 — CRLF / trailing-newline policy:** must the tool preserve CRLF line endings and
  the file's final-newline state exactly? This interacts directly with the idempotence
  guarantee. *(Default: normalize to LF, ensure single trailing newline; revisit if you
  edit on Windows.)*

**Resolution (2026-07-12):** user accepted all four defaults verbatim. So for MVP:
Setext headings out of scope (ATX only); skip only the leading first-heading H1;
exit codes `0` ok / `1` stale / `2` usage-IO error; normalize line endings to LF with a
single trailing newline. These are now constraints, not open questions.
