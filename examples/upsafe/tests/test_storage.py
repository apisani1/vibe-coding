import hashlib
import io
import os

import pytest

from upsafe import storage
from upsafe.errors import EmptyUpload, FileTooLarge, PathEscape
from upsafe.storage import open_within_root, store_stream


def _files(quarantine_dir):
    """Published (non-temp) files in the quarantine."""
    return [p for p in quarantine_dir.iterdir() if not p.name.startswith(".tmp-")]


def _temps(quarantine_dir):
    return [p for p in quarantine_dir.iterdir() if p.name.startswith(".tmp-")]


def test_stores_bytes_with_correct_size_and_sha256(tmp_path):
    q = tmp_path / "quarantine"
    payload = b"hello upsafe" * 1000
    result = store_stream(q, io.BytesIO(payload), max_bytes=10 * 1024 * 1024)
    assert result.size == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    stored = q / result.stored_name
    assert stored.read_bytes() == payload
    assert _temps(q) == []  # no leftover temp


class _CountingReader:
    """Yields ``total`` bytes; raises if read past ``hard_limit`` (proves early abort)."""

    def __init__(self, total, hard_limit):
        self.remaining = total
        self.read_total = 0
        self.hard_limit = hard_limit

    def read(self, n):
        if self.read_total >= self.hard_limit:
            raise AssertionError(f"over-read past hard_limit={self.hard_limit}")
        give = min(n, self.remaining)
        self.remaining -= give
        self.read_total += give
        return b"a" * give


def test_oversize_aborts_early_with_no_residue(tmp_path):
    q = tmp_path / "quarantine"
    chunk = 1024
    max_bytes = 4096
    reader = _CountingReader(total=1_000_000, hard_limit=max_bytes + chunk + 1)
    with pytest.raises(FileTooLarge):
        store_stream(q, reader, max_bytes=max_bytes, chunk_size=chunk)
    # aborted after at most one chunk past the cap, never reading the whole stream
    assert reader.read_total <= max_bytes + chunk
    assert _files(q) == [] and _temps(q) == []


class _MaxBufferReader:
    def __init__(self, total):
        self.remaining = total
        self.max_returned = 0

    def read(self, n):
        give = min(n, self.remaining)
        self.remaining -= give
        self.max_returned = max(self.max_returned, give)
        return b"x" * give


def test_peak_buffer_bounded_by_chunk_size(tmp_path):
    q = tmp_path / "quarantine"
    chunk = 4096
    reader = _MaxBufferReader(total=chunk * 50)  # 50x the chunk
    store_stream(q, reader, max_bytes=10 * 1024 * 1024, chunk_size=chunk)
    # no single read returned more than one chunk, independent of total size
    assert reader.max_returned <= chunk


def test_empty_upload_rejected_with_no_residue(tmp_path):
    q = tmp_path / "quarantine"
    with pytest.raises(EmptyUpload):
        store_stream(q, io.BytesIO(b""), max_bytes=1024)
    assert _files(q) == [] and _temps(q) == []


def test_durability_ordering_temp_fsync_then_rename_then_dir_fsync(tmp_path, monkeypatch):
    q = tmp_path / "quarantine"
    events = []
    real_fsync, real_rename = os.fsync, os.rename

    def spy_fsync(fd):
        events.append("fsync")
        return real_fsync(fd)

    def spy_rename(src, dst):
        events.append("rename")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    monkeypatch.setattr(os, "rename", spy_rename)
    store_stream(q, io.BytesIO(b"payload"), max_bytes=1024)

    assert "rename" in events
    r = events.index("rename")
    assert "fsync" in events[:r], "temp file must be fsync'd before rename"
    assert "fsync" in events[r + 1 :], "quarantine dir must be fsync'd after rename"


def test_post_publish_error_unlinks_published_file(tmp_path, monkeypatch):
    q = tmp_path / "quarantine"

    def boom(_path):
        raise RuntimeError("dir fsync failed")

    monkeypatch.setattr(storage, "_fsync_dir", boom)
    with pytest.raises(RuntimeError):
        store_stream(q, io.BytesIO(b"payload"), max_bytes=1024)
    # published file was cleaned up — no dangling artifact
    assert _files(q) == [] and _temps(q) == []


def test_open_within_root_accepts_normal_name(tmp_path):
    q = tmp_path / "quarantine"
    q.mkdir()
    assert open_within_root(q, "abcd1234") == (q / "abcd1234").resolve()


@pytest.mark.parametrize(
    "evil",
    ["../evil", "../../etc/passwd", "/etc/passwd", "sub/../../x", "a\\b", "", ".", ".."],
)
def test_open_within_root_rejects_escaping_or_degenerate_names(tmp_path, evil):
    q = tmp_path / "quarantine"
    q.mkdir()
    with pytest.raises(PathEscape):
        open_within_root(q, evil)
