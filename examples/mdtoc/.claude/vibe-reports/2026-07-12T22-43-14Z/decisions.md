# Design decisions

## D1: Pure `render(text) -> text` core, I/O only in the CLI
- Decision: implement the whole transform as a pure string function; confine file reads,
  writes, and `sys.exit` to `cli.py`.
- Alternatives considered: a `Document` class holding file path + mutation methods
  (rejected — statefulness buys nothing for a one-shot transform and complicates tests);
  doing IO inside the core (rejected — couples logic to the filesystem).
- Consequences: idempotence and `--check` become one-line comparisons on strings; unit
  tests are string-in/string-out with no temp files for the core logic. Slightly more
  wiring in `cli.py`.

## D2: Idempotence via a single canonical `render`, not a diff/patch
- Decision: define "current" as `render(text) == text`; the writer emits `render(text)`,
  `--check` compares against it. No separate staleness detector.
- Alternatives considered: parse the existing TOC and compare entry-by-entry (rejected —
  a second code path that can disagree with the writer, reintroducing the exact drift the
  tool exists to prevent).
- Consequences: `--check` and write are provably consistent. Requires `render` to be a
  true fixed point, which pins the whitespace/trailing-newline contract as part of the
  spec, not an afterthought.

## D3: Standard library only — replicate Python-Markdown slugging, don't import it
- Decision: copy Python-Markdown's `slugify()` + `unique()` (the `_1`/`_2` collision
  scheme) into `slug.py`; zero runtime dependencies.
- Alternatives considered: `import markdown` and reuse its toc slugger (rejected — drags
  in a full Markdown parser and couples our output to a transitive version we don't
  control); a Markdown AST parser like `mistune` (rejected — over-engineered for ATX
  heading extraction).
- Consequences: behavior is pinned by our own tests and stable across environments; if
  Python-Markdown changes its algorithm we are intentionally decoupled. Cost: we own the
  fidelity and must test it against known Python-Markdown outputs.

## D4: LF normalization + single trailing newline
- Decision: normalize CRLF/CR to LF and guarantee exactly one trailing newline in the
  output; do not preserve CRLF.
- Alternatives considered: detect and preserve the file's original line-ending style
  (rejected for MVP — adds state to the "fixed point" and complicates idempotence for a
  case the user accepted as out-of-scope).
- Consequences: simplest possible idempotence contract; a CRLF file is reported stale and
  converted on first write. Revisit if Windows-authored docs become a real use case.

## D5: Marker semantics — exactly one well-formed pair, fence-aware, else error (exit 2)
- Decision: require the first `<!-- toc -->` followed by a `<!-- /toc -->`; missing →
  `MissingMarkersError`, malformed ordering / double-open → `MalformedMarkersError`; both
  exit 2 and leave the file untouched. Match markers by stripped whole-line equality.
  **`find_markers` shares the fenced-code tracking used for heading scanning, so markers
  inside a code fence are ignored** (architect review): a README documenting mdtoc's own
  syntax won't false-trigger a region or a spurious `MalformedMarkersError`.
- Alternatives considered: auto-insert markers when absent (explicitly rejected in the
  spec interview — erroring is safer); support multiple TOC regions (deferred — no MVP
  need); fence-blind marker matching (rejected — breaks on the tool's own docs).
- Consequences: the tool never rewrites a file the user didn't opt in to manage.
  Whole-line stripped matching tolerates leading/trailing whitespace but not inline
  markers mid-line — acceptable and predictable. Fence-awareness is shared with the
  scanner, so there is one fence model, not two.

## D6: Exit codes 0 / 1 / 2
- Decision: `0` success or already-current; `1` stale (only reachable via `--check`);
  `2` usage / IO / marker errors.
- Alternatives considered: any-non-zero-for-everything (rejected — CI can't distinguish
  "stale TOC" from "the file doesn't exist", which are different failures).
- Consequences: CI can branch on staleness vs. hard error. Matches the user-accepted
  default from the define interview.

## D6b: Blank line surrounding the TOC body (pinned whitespace contract)
- Decision: the splice places exactly one blank line between each marker and the body
  (`<!-- toc -->` ⏎ ⏎ body ⏎ ⏎ `<!-- /toc -->`); an empty TOC leaves a single blank line
  between the markers.
- Alternatives considered: body directly adjacent to the markers, no blank lines
  (rejected — the architect flagged that some CommonMark renderers won't start a list
  immediately after the comment; also leaves the contract implicit). Both forms are
  idempotent; the blank-line form additionally renders reliably.
- Consequences: the whitespace contract is explicit and pinned by an idempotence test,
  not an accident of implementation. It is load-bearing for the fixed point, so it lives
  in a decision rather than a comment.

## D7: Relative indentation, 2-space unit
- Decision: indent by `(level - min_kept_level)`, two spaces per unit.
- Alternatives considered: absolute indentation by heading level (rejected — a doc that
  starts at H2 would be over-indented and could render as a code block); 4-space unit
  (rejected — 2 spaces is the common `markdown-toc` convention and renders as nested
  lists in CommonMark).
- Consequences: TOCs read naturally regardless of the document's shallowest level. The
  2-space choice is pinned by tests as part of the idempotence contract.

## D8: Four modules, not six — fold `toc.py` and `errors.py` into `document.py`
- Decision: keep `slug.py`, `headings.py`, `document.py`, `cli.py` (+ `__main__.py`).
  `build_toc` and the three-class error hierarchy live inside `document.py`.
- Alternatives considered: a module per pipeline stage incl. separate `toc.py`/`errors.py`
  (rejected on the architect's simplicity finding — neither has a second consumer, and
  both are pure transforms behind `render`); one monolithic module (rejected — `slug` and
  `headings` are genuine, independently testable seams worth keeping).
- Consequences: fewer files to navigate for a ~150-line tool while preserving the two
  seams that carry the trickiest logic (slug fidelity, fence-aware scanning). `cli.py`
  imports the error types from `document.py`.

## D9: Scan headings only outside the managed marker region
- Decision: `render` feeds `parse_headings` the document with `lines[open_i:close_i+1]`
  removed, so TOC bullets never enter heading/fence detection.
- Alternatives considered: scan the whole document and rely on TOC bullets not resembling
  headings or fences (rejected — the architect showed the fixed point would then depend on
  incidental bullet content; a bullet or heading text beginning `~~~` could desync the
  fence counter).
- Consequences: the fence counter and heading scan are provably independent of whatever
  the generated TOC contains, hardening the idempotence guarantee. Marginal extra list
  slicing in `render`.
