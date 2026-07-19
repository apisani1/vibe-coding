# Verification plan

Upstream spec:   .claude/vibe-reports/2026-07-18T17-03-13Z/spec.md
Upstream design: .claude/vibe-reports/2026-07-18T17-09-56Z/design.md
Upstream plan:   .claude/vibe-reports/2026-07-18T17-30-16Z/plan.md

Toolchain (planned; no checks exist yet — greenfield repo): `uv run pytest`
with httpx / Starlette `TestClient`; `make pre-commit` (black, isort, flake8,
pylint, mypy). All checks are executed with `uv run` against Python 3.12.

## Criteria

What "good" means, per spec acceptance criterion. Each row is the observable
pass condition; the layer notes where the truth is cheapest to observe.

1. **Auth enforced.** No/invalid API key on `POST /uploads` → 401/403 AND zero
   new files under quarantine AND zero new DB rows. Correct key + permitted file
   → 201 with a token. Observed at the auth-dependency unit layer and the HTTP
   layer (with a filesystem+DB side-effect snapshot on the reject path).
2. **Allow-list by extension.** Disallowed extension (`.exe`) → 4xx (415) and
   nothing persisted (no file, no row). Observed at validation unit + HTTP layer.
3. **Allow-list by content signature.** Permitted extension but mismatched magic
   bytes (script bytes named `.png`) → 4xx (415), nothing persisted. The
   load-bearing guards are binary magic-byte match and text safety (valid UTF-8,
   no NUL/control). The `<`-leading flag is optional (D1) and NOT a pass gate.
4. **Size limit.** Body > `MAX_UPLOAD_BYTES` → 413 raised mid-stream, no partial
   file left in quarantine, and the server does not buffer the whole body. The
   memory claim is proven at the storage layer (bounded chunk buffer) + a
   deterministic streaming-abort; peak-memory-bound e2e is secondary.
5. **Path-traversal defense.** For `../../etc/passwd`, `..\\..\\x`, absolute
   paths, and NUL/control-byte filenames: bytes stored under a server-generated
   random name strictly inside the quarantine root; NO file created or read
   anywhere outside that root. Proven structurally: (a) original filename is
   never a path component, (b) resolved write path `startswith` realpath(root),
   (c) `open_within_root` rejects a crafted escaping name, (d) filesystem outside
   the root is unchanged by an adversarial upload.
6. **Random storage names.** Two uploads of identical content → two distinct,
   high-entropy on-disk names and two distinct tokens; neither name equals nor
   contains the original filename. Token/name format + entropy checked at the
   `tokens` unit layer.
7. **Token round-trip.** Token from a 201 retrieves the exact original bytes
   (sha256 of downloaded == sha256 returned at upload) via `GET /downloads/{token}`
   with `Content-Disposition: attachment`, server-resolved `Content-Type`, and
   `X-Content-Type-Options: nosniff`.
8. **Token opacity.** A syntactically valid non-existent token and an expired
   token both return 404 with byte-identical bodies and equal header sets (modulo
   `Date`); nothing distinguishes the two cases in the response.
9. **Expiry.** A token past its TTL → 404 and the object is unavailable. Verified
   at the metadata layer (`get_object` returns None when `expires_at <= now`) and
   the HTTP layer (expired token → 404).
10. **No secret leakage.** Across a full upload+download cycle, captured
    application logs contain none of: the API key, the download token, the
    original filename bytes, or the file contents. Verified by scanning captured
    log output for unique sentinel values.
11. **Filename sanitization on the way out.** `Content-Disposition` carries a
    sanitized original name — no CR/LF, `;`, quotes, or path separators; unicode
    via percent-encoded RFC 5987 `filename*` — so a malicious filename cannot
    inject headers.
12. **Health check.** `GET /healthz` → 200 without auth, body exposes no
    stored-file or config data.

## Checks

Smallest sufficient set. Each check names the criterion/claim it proves and the
planned test file. Commands are the plan's checkpoint `verify:` lines.

**Storage & primitives (Phase A — run before HTTP exists)**

- `test_tokens.py` — `new_token()`/`new_stored_name()` produce URL-safe strings,
  distinct across calls, with the expected length/entropy; token != stored_name.
  Proves **6** (entropy/format) and the primitive behind **5/8**.
  Command: `uv run pytest tests/test_tokens.py`.
- `test_metadata.py` — insert+lookup by token; `get_object` returns None when
  `expires_at <= now`; UNIQUE constraint on `stored_name` rejects a duplicate.
  Proves **9** (expiry semantics) and the collision-safety behind **6**.
  Command: `uv run pytest tests/test_metadata.py`.
- `test_storage.py` —
  - sha256 + size returned by `store_stream` match the input bytes → underpins **7**.
  - **Streaming abort (load-bearing for 4):** feed a reader of `MAX+delta` bytes
    that raises if read past `MAX + one_chunk`; assert `store_stream` aborts with
    the size error before over-reading, and the `.tmp-*` file is unlinked (no
    residue). Proves **4** streaming + cleanup deterministically.
  - **Bounded-memory (load-bearing for 4):** feed a large synthetic stream through
    a reader that records the max single buffer requested; assert it stays
    `<= chunk_size + const`, independent of total size → proves no whole-body buffer.
  - `open_within_root` rejects a crafted `stored_name` containing `../`/absolute
    escape and accepts a normal name; assert resolved path `startswith`
    realpath(root). Proves the guard behind **5**.
  - **Durability ordering (partial):** spy `os.fsync`/`os.rename` and assert temp
    is fsync'd before rename and the quarantine dir is fsync'd before the caller
    commits metadata; simulate insert-fails-after-publish → published file unlinked,
    no dangling artifact. Proves the observable part of the crash-consistency claim.
  Command: `uv run pytest tests/test_storage.py`.

**Validation (Phase B)**

- `test_validation.py` —
  - `check_extension` rejects `.exe` / accepts allow-listed → proves **2**.
  - `sniff_signature` rejects script bytes under a `.png` name; accepts real PNG
    magic → proves **3** (binary path).
  - `is_safe_text` rejects NUL/control bytes and invalid UTF-8; accepts clean
    UTF-8 → proves **3** (text path) and the NUL facet of **5** at unit level.
  - `content_disposition` on `evil"\r\nX-Injected:1; name=../a` strips
    CR/LF/`;`/quotes/path-seps and emits percent-encoded `filename*` → proves **11**.
  Command: `uv run pytest tests/test_validation.py`.

**Auth & logging (Phase B)**

- `test_auth.py` — `require_api_key` rejects missing/wrong key (401), accepts the
  configured key (constant-time compare path exercised) → proves the dependency
  behind **1**.
- `test_logging.py` — invoke `log_request` for a sample request carrying a
  sentinel key/token/filename; capture the emitted record and assert the output
  contains only the field allow-list (method/path/status/size/duration) and none
  of the sentinels → first proof of **10**.
  Command: `uv run pytest tests/test_auth.py tests/test_logging.py`.

**Upload endpoint (Phase B)**

- `test_upload.py` —
  - Happy path: correct key + PNG → 201 with `{token, original_name, content_type,
    size, sha256, expires_at}` → proves **1** (accept half) and feeds **7**.
  - No/invalid key → 401 AND snapshot proves no new quarantine file and no new DB
    row → proves **1** (reject half).
  - Oversize body → 413, and quarantine has no leftover `.tmp-*`/published file →
    proves **4** HTTP behavior. Optionally assert an e2e peak-memory bound using a
    streaming request body and pinned Starlette (secondary, best-effort).
  - Disallowed extension → 415, nothing persisted → proves **2** HTTP.
  - Bad magic (script as `.png`) → 415, nothing persisted → proves **3** HTTP.
  - Empty / zero-byte / multi-part / no-part → 400 → edge-case coverage.
  Command: `uv run pytest tests/test_upload.py`.

**Download & health (Phase B)**

- `test_download.py` —
  - Round-trip: upload then GET token; downloaded sha256 == upload sha256; assert
    `Content-Disposition: attachment`, correct `Content-Type`,
    `X-Content-Type-Options: nosniff` → proves **7** and **11** (header present).
  - Opacity: request a well-formed non-existent token and an expired token; assert
    both are 404 with identical `response.content` and equal header sets modulo
    `Date` → proves **8**.
  - Expired token → 404 → proves **9** HTTP.
  - `GET /healthz` → 200 without auth; body has no config/file data → proves **12**.
  Command: `uv run pytest tests/test_download.py`.

**Cross-cutting adversarial (Phase C)**

- `test_e2e_security.py` —
  - Traversal variants (`../../etc/passwd`, `..\\..\\x`, absolute, NUL/control):
    snapshot files outside the resolved quarantine root before/after; assert zero
    change outside, exactly the expected new file inside, stored_name matches the
    CSPRNG pattern and contains no substring of the original name → proves **5**.
  - Full upload→download cycle with sentinel API key + known contents + sentinel
    filename; capture all app-logger handlers into a buffer; assert none of the
    sentinels appear → completes **10**.
  - Two identical-content uploads → distinct stored names AND distinct tokens →
    completes **6**.
  Command: `uv run pytest` (full suite) then `make pre-commit`.

**Gate checks**

- `uv run pytest` full suite green (all criteria).
- `uv run python -c "import upsafe"` imports (CP1 smoke).
- `make pre-commit` → black/isort/flake8/pylint/mypy clean (style/type gate).

## External signals

- **Captured application log output** — the primary external signal, consumed by
  `test_logging.py` and `test_e2e_security.py`. Capture via a dedicated
  `StreamHandler(StringIO)` attached to the upsafe logger (do not rely on `caplog`
  alone, which can miss non-propagating handlers). Scan for sentinel values.
- **Filesystem state under a per-test `tmp_path` data root** — the quarantine
  directory and `upsafe.db`. Used as a signal for "nothing persisted" (criteria
  1/2/3), "no partial file" (4), and "nothing outside root" (5). Snapshot the file
  set before/after and diff.
- **SQLite `objects` table** — row count / presence used to prove persistence and
  non-persistence side effects.
- **Response bytes and header sets** — the signal for criteria 7/8/11/12.
- **`uvicorn` access log** — NOT produced under TestClient; unavailable as a test
  signal (see Cannot be verified).

## Risk-based expansion

Run the full suite by default (it is small). Expand or add depth when:

- **Starlette / python-multipart version bumps** — re-run `test_upload.py`
  oversize + peak-memory checks; the `max_part_size` abort and the
  `SpooledTemporaryFile` spool threshold are load-bearing framework internals
  (design). A dependency change here is the top expansion trigger; pin the version
  and treat a peak-memory regression as blocking.
- **Any change to `storage.py` (streaming/atomic/traversal)** — re-run the full
  `test_storage.py` plus the `test_e2e_security.py` traversal matrix; this module
  owns three of the five hardest claims (4, 5, durability).
- **Any change to `validation.py` allow-list or signature table** — re-run
  `test_validation.py` and the upload reject paths; a new allow-listed type MUST
  ship with a new magic-byte signature and its own reject-the-mismatch test.
- **Any change to `logging.py` or the request-log field list** — re-run the log
  scans (10); a new logged field is the most likely accidental leak vector.
- **Cross-module / public-API changes (routes, app factory, response model)** —
  run the full e2e suite, not just the touched unit test.
- **Token/entropy or auth-compare changes** — re-run `test_tokens.py` +
  `test_auth.py`; regenerate opacity assertions in `test_download.py`.

## Cannot be verified

Declared up front — impossible or unreliable in a local pytest/TestClient run:

- **True crash-consistency / durability across power loss.** We can verify
  operation ORDERING (fsync-before-rename, dir-fsync-before-commit) and cleanup
  (orphan-not-dangling-row), but NOT that `fsync` reaches stable storage or that
  the guarantee survives a real kernel/power crash. That needs fault injection
  (e.g. `dm-flakey`, power-cut harness, syscall interception) outside this scope.
- **Timing-channel indistinguishability of token lookup (criterion 8).** Byte-
  identical bodies/status are verified; constant-time lookup is asserted by code
  inspection only — test-measured timing is too noisy to gate on.
- **Constant-time API-key comparison as a timing property (constraint 6).** We
  verify `secrets.compare_digest` is on the code path; we do not measure timing.
- **End-to-end peak-memory under real load (criterion 4, strong form).** The
  TestClient/httpx builds the request body in-process, confounding a whole-request
  memory measurement. The streaming claim is proven at the storage layer instead;
  the e2e memory bound is best-effort only. True under-load memory behavior would
  need a separate out-of-process load test against a running uvicorn.
- **uvicorn access-log redaction (criterion 10, production form).** TestClient does
  not emit uvicorn access logs, so the production access-log line cannot be scanned
  here. Requires manual review of the deployed access-log format (or disabling it).
- **TLS / transport security.** Out of scope by spec (fronting proxy); tokens are
  bearer capabilities and their in-transit protection is not verifiable locally.
- **Malware/malicious-content safety of permitted-type files.** Explicitly out of
  scope (allow-list + quarantine is the boundary, not content scanning).
- **Multi-node SQLite concurrency / physical expiry purge.** Out of scope (single
  node; read-time expiry only; sweeper deferred).
