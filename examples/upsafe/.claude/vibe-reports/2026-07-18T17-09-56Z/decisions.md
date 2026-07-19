# Design decisions

Upstream spec: .claude/vibe-reports/2026-07-18T17-03-13Z/spec.md

## D1: Hand-rolled content-signature table instead of a sniffing library

- **Decision:** Detect file type from a small in-repo table of magic-byte prefixes for the
  allow-listed binary types, plus a strict text-safety check for text types. No
  `python-magic` / `filetype` dependency.
- **Alternatives considered:** `python-magic` (rejected — pulls in the `libmagic` system
  library, an out-of-repo trusted component with a large surface); `filetype` (rejected —
  pure-Python but still an added third-party trusted dependency for a job that is ~20 lines
  given a tiny static allow-list); extension-only checking (rejected — fails acceptance
  criterion 3, a script renamed `.png`).
- **Consequences:** Minimal trusted surface and full auditability; every supported type's
  detection is visible and unit-testable. Cost: adding a new allowed type requires adding
  its signature; text detection is heuristic (UTF-8 + no NUL/control + not an HTML/script
  lead), which is deliberately conservative.

## D2: Use Starlette's multipart parser with `max_part_size`, not a hand-rolled streaming parser

- **Decision:** Configure Starlette's multipart parsing with `max_part_size =
  MAX_UPLOAD_BYTES` (and `max_files = 1`) so oversize bodies abort mid-stream; add a
  redundant running byte-count guard while copying the part to the temp file.
- **Alternatives considered:** Hand-rolling a streaming multipart parser over
  `request.stream()` with `python-multipart` callbacks (rejected — reimplements
  security-critical parsing that framework code already does and tests; *more* hand-written
  attack surface, contrary to the service's goal); accepting `UploadFile` and checking size
  after the fact (rejected — reads the whole body first, violating the "don't buffer whole
  body / abort early" criterion).
- **Consequences:** Streaming abort comes from well-tested code; our code stays thin. We
  depend on Starlette's `max_part_size` semantics — pinned and verified during build
  against the installed version. Defense-in-depth byte counter covers any parser surprise.

## D3: On-disk name distinct from the download token

- **Decision:** Generate two independent random values per upload: `token`
  (`token_urlsafe(32)`, the capability) and `stored_name` (`token_hex(16)`, the filename).
  The token is only ever a SQLite key; it never appears on the filesystem.
- **Alternatives considered:** Using the token as the filename (rejected — couples the
  capability to a filesystem path, and any path-handling bug would expose or be driven by
  the secret; separation keeps the token off the disk entirely).
- **Consequences:** The user-controlled request value (`token`) touches only a DB
  primary-key lookup, making path traversal structurally impossible on download. Slightly
  more metadata; trivially worth it.

## D4: Publish file before inserting metadata (crash-consistency ordering)

- **Decision:** Stream to temp → fsync → atomic rename to final name → *then* insert the DB
  row; on insert failure, unlink the published file.
- **Alternatives considered:** DB-row-first then write file (rejected — a crash in between
  yields a token that 500s on download, i.e. a live-looking capability over a missing
  file); single transaction spanning disk+DB (not available across two stores).
- **Consequences:** Worst-case residue is an unreachable orphan file (no token), which a
  future sweeper reclaims — never a dangling capability. Aligns with the "persists nothing
  on reject / no dangling rows" criteria.

## D5: Configuration via a frozen dataclass, not pydantic-settings

- **Decision:** `load_settings()` reads env vars into an immutable `Settings` dataclass,
  validating required values (fail fast if `UPSAFE_API_KEY` is unset/blank).
- **Alternatives considered:** `pydantic-settings` (rejected — an extra dependency for a
  handful of env vars; FastAPI already gives us Pydantic for response models, but settings
  don't need it); reading `os.environ` ad hoc in routes (rejected — scatters config, hard
  to test, no fail-fast).
- **Consequences:** One typed, test-injectable config object; `create_app(settings)` takes
  it as an argument (separate creation from use), so tests build apps with tmp data roots
  and known keys. No extra dependency.

## D6: Token model — expiring, multi-use; read-time expiry enforcement

- **Decision:** Tokens are valid until `expires_at` (created_at + `TOKEN_TTL`, default 24h)
  and usable any number of times until then. Expiry is checked at download time; expired
  files are not physically deleted in the MVP.
- **Alternatives considered:** Single-use tokens (deferred per spec — needs careful
  concurrency handling); non-expiring (rejected — weakest posture); background sweeper
  (deferred — read-time check is sufficient for correctness, sweeper is an ops optimization).
- **Consequences:** Simple, predictable, no delete/concurrency races. Disk grows with
  expired files until a sweeper is added (documented limitation).

## D8: Dedicated redacting-logging helper owns criterion 10

- **Decision:** A small `logging.py` provides `configure_logging` + `log_request`, which
  emit an explicit field allow-list per request (method, path, status, size, duration).
  Token, API key, original-filename bytes, and file contents are never logged fields.
- **Alternatives considered:** Relying on uvicorn/Starlette default access logs (rejected —
  they can include query strings/paths and give no redaction contract to test); ad-hoc
  `logging` calls in routes (rejected — no single place to prove criterion 10).
- **Consequences:** Criterion 10 ("no secret leakage") has one auditable owner and a
  log-scan test target. Origin: vibe-architect design review (risk finding).

## D9: Durability ordering — fsync the quarantine dir before committing metadata

- **Decision:** After `os.rename` publishes the file, `fsync` the quarantine directory so
  the rename is durable, and only then commit the SQLite metadata row.
- **Alternatives considered:** fsync the temp file only, then rename + insert (rejected —
  on power loss after the metadata commit but before the rename is persisted, a committed
  token could point at a missing file: a 500-on-download "dangling capability", exactly
  what D4 claims is impossible).
- **Consequences:** The D4 guarantee ("never a row over a missing file") is actually
  pinned by the durability order; worst residue stays an unreachable orphan. Origin:
  vibe-architect design review (risk finding).

## Note on D1 (accepted from architect review)

The text-safety check's load-bearing part is **valid UTF-8 + no NUL/control bytes**. The
leading-`<` HTML/script rejection is demoted to an *optional* conservative flag, not a hard
guard, because `attachment` + `nosniff` already prevent inline rendering and the heuristic
can false-positive on legitimate `<`-leading text/CSV. Documented so it is not mistaken for
a security requirement. `stored_name` collision (128-bit) is caught belt-and-suspenders by
the UNIQUE constraint on insert — negligible probability, no wrong-file service.

## D7: Reject empty (zero-byte) uploads

- **Decision:** A zero-byte file part is a 400.
- **Alternatives considered:** Storing empty files (rejected — nothing to validate by
  signature, no legitimate MVP use, and it muddies the "valid file" contract).
- **Consequences:** `sniff_signature`/`is_safe_text` always have bytes to inspect; simpler
  invariants. If a real empty-file use case appears, revisit.

## D10: Transport-layer body cap + disabled uvicorn access log (post-review security fixes)

Added after two P1 findings from an external (Codex) security review that the vibe
verify/review passes missed.

- **Decision (corrects D2):** `max_part_size` does NOT bound multipart *file* parts in
  Starlette 1.3.1 (confirmed in `formparsers.MultiPartParser.on_part_data`: the size check
  is inside `if self._current_part.file is None`; file parts stream to a
  `SpooledTemporaryFile` unchecked). D2's premise — that `max_part_size` gives a streaming
  file-size abort — was wrong. A large upload was therefore spooled in full (memory→disk)
  before `store_stream`'s late 413, enabling temp-filesystem exhaustion by an authenticated
  client. Fix: `middleware.BodySizeLimitMiddleware` counts body bytes off the ASGI
  `receive` channel (plus a `Content-Length` fast path) and returns 413 before the body is
  buffered. `store_stream` remains the exact per-file arbiter; the middleware limit is
  `max_upload_bytes + MULTIPART_OVERHEAD_ALLOWANCE` (single-part framing headroom).
- **Alternatives considered:** hand-rolling a streaming multipart parser writing straight to
  the quarantine temp (rejected — larger security-critical surface than a ~40-line body cap,
  and it fully reverses D2 rather than layering a fix); a `Content-Length`-only check
  (insufficient — chunked/absent/spoofed length).
- **Decision (corrects the shipped entrypoint vs D8):** `__main__.py` now runs uvicorn with
  `access_log=False`. Uvicorn's default access log records the request line
  `GET /downloads/<token>`, leaking the download capability — exactly what D8 rejected. The
  app's own redacting `log_request` covers observability. (This gap was flagged as a known
  un-verified limitation in verify but never fixed until now.)
- **Consequences:** the size cap is now genuinely enforced without buffering the whole body
  (acceptance criterion 4 holds end-to-end, not just at the storage layer); download tokens
  no longer reach process/access logs. Verified: a 5 MiB upload under a 1 MiB limit now
  returns 413 (previously 201). Tests: `tests/test_middleware.py` (unit — early abort) +
  `tests/test_upload.py::test_oversize_body_rejected_before_reaching_storage` (integration —
  `store_stream` never reached).
