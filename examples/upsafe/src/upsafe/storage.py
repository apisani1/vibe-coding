"""Quarantine storage: streaming writer, atomic publish, traversal-safe reopen.

This module owns three of the hardest security claims:

- **Bounded-memory streaming with a hard size cap.** ``store_stream`` reads the source in
  fixed chunks, never materializing the whole body, and aborts the moment the running
  byte count exceeds ``max_bytes`` — deleting the temp file so nothing partial is left.
- **Atomic, crash-consistent publish (design D9).** Bytes go to a ``.tmp-*`` file inside
  the quarantine, are ``fsync``'d, atomically ``rename``'d to the final random name, and
  then the quarantine *directory* is ``fsync``'d. Callers commit metadata only after this
  returns, so a committed token never points at a missing file.
- **Traversal-safe reopen.** ``open_within_root`` resolves the candidate path and refuses
  (``PathEscape``) anything outside the quarantine root. On-disk names are server-generated
  so this is belt-and-suspenders, not the primary defense.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .errors import (
    EmptyUpload,
    FileTooLarge,
    PathEscape,
)
from .tokens import new_stored_name

DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KiB — the upper bound on peak per-request buffer.


@dataclass(frozen=True)
class StoreResult:
    stored_name: str
    size: int
    sha256: str


def quarantine_path(quarantine_dir: Path, stored_name: str) -> Path:
    return quarantine_dir / stored_name


def _fsync_dir(path: Path) -> None:
    """fsync a directory so a rename within it is durable (D9)."""
    dir_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def store_stream(
    quarantine_dir: Path,
    source: BinaryIO,
    *,
    max_bytes: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> StoreResult:
    """Stream ``source`` into the quarantine under a fresh random name.

    Reads at most ``chunk_size`` bytes at a time (bounded memory). Raises ``FileTooLarge``
    the moment the running size exceeds ``max_bytes`` and ``EmptyUpload`` for a zero-byte
    source — deleting the temp file in either case (nothing partial persists). On success
    the file is durably published and its ``StoreResult`` returned.
    """
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", dir=quarantine_dir)
    tmp_path = Path(tmp_name)
    final_path: Path | None = None
    try:
        with os.fdopen(fd, "wb") as tmp:
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise FileTooLarge(f"upload exceeds max_bytes={max_bytes}")
                digest.update(chunk)
                tmp.write(chunk)
            tmp.flush()
            os.fsync(tmp.fileno())
        if size == 0:
            raise EmptyUpload("upload is empty")
        stored_name = new_stored_name()
        final_path = quarantine_path(quarantine_dir, stored_name)
        os.rename(tmp_path, final_path)
        _fsync_dir(quarantine_dir)
    except BaseException:
        # Nothing partial survives: unlink the published file if we got that far,
        # otherwise the temp file.
        if final_path is not None:
            with contextlib.suppress(FileNotFoundError):
                final_path.unlink()
        with contextlib.suppress(FileNotFoundError):
            tmp_path.unlink()
        raise
    return StoreResult(stored_name=stored_name, size=size, sha256=digest.hexdigest())


def open_within_root(quarantine_dir: Path, stored_name: str) -> Path:
    """Resolve ``stored_name`` under the quarantine and assert it stays inside the root.

    Returns the resolved path (for the caller to serve). Raises ``PathEscape`` if the
    resolved path would fall outside the quarantine root, or if ``stored_name`` is empty
    or contains a path separator — a fail-closed invariant guard.
    """
    if not stored_name or "/" in stored_name or "\\" in stored_name or stored_name in {".", ".."}:
        raise PathEscape(f"invalid stored_name {stored_name!r}")
    root = quarantine_dir.resolve()
    candidate = (quarantine_dir / stored_name).resolve()
    if root not in candidate.parents:
        raise PathEscape(f"resolved path {candidate} escapes quarantine root {root}")
    return candidate
