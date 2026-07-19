import pytest

from upsafe.config import DEFAULT_ALLOWED_TYPES
from upsafe.errors import TypeNotAllowed
from upsafe.validation import (
    check_extension,
    content_disposition,
    extract_extension,
    is_safe_text,
    resolve_type,
    sniff_signature,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"junk"
GIF_MAGIC = b"GIF89a" + b"...."
PDF_MAGIC = b"%PDF-1.7\n%stuff"
SCRIPT = b"#!/bin/sh\nrm -rf /\n"


@pytest.mark.parametrize(
    "name,expected",
    [("photo.PNG", "png"), ("a.tar.gz", "gz"), ("noext", ""), ("../../x.pdf", "pdf")],
)
def test_extract_extension(name, expected):
    assert extract_extension(name) == expected


def test_check_extension_allows_listed():
    assert check_extension("photo.png", DEFAULT_ALLOWED_TYPES) == "png"


def test_check_extension_rejects_unlisted():
    with pytest.raises(TypeNotAllowed):
        check_extension("evil.exe", DEFAULT_ALLOWED_TYPES)


def test_check_extension_rejects_no_extension():
    with pytest.raises(TypeNotAllowed):
        check_extension("noext", DEFAULT_ALLOWED_TYPES)


@pytest.mark.parametrize(
    "ext,head",
    [("png", PNG_MAGIC), ("jpg", JPEG_MAGIC), ("jpeg", JPEG_MAGIC), ("gif", GIF_MAGIC), ("pdf", PDF_MAGIC)],
)
def test_sniff_signature_accepts_matching_magic(ext, head):
    assert sniff_signature(ext, head) is True


def test_sniff_signature_rejects_script_as_png():
    assert sniff_signature("png", SCRIPT) is False


def test_sniff_signature_text_types_have_no_signature():
    assert sniff_signature("txt", SCRIPT) is True  # deferred to is_safe_text


def test_is_safe_text_accepts_utf8_including_multibyte():
    assert is_safe_text("hello, café — 日本語\n\tok\r\n".encode("utf-8")) is True


def test_is_safe_text_rejects_nul():
    assert is_safe_text(b"ok\x00then") is False


def test_is_safe_text_rejects_control_bytes():
    assert is_safe_text(b"ok\x07bell") is False  # BEL


def test_is_safe_text_rejects_invalid_utf8():
    assert is_safe_text(b"\xff\xfe\xfd") is False


def test_is_safe_text_tolerates_split_multibyte_at_boundary():
    # a 3-byte char cut after 2 bytes must not be treated as invalid
    assert is_safe_text("日".encode("utf-8")[:2]) is True


def test_resolve_type_binary_happy_path():
    assert resolve_type("png", PNG_MAGIC, DEFAULT_ALLOWED_TYPES) == "image/png"


def test_resolve_type_rejects_script_as_png():
    with pytest.raises(TypeNotAllowed):
        resolve_type("png", SCRIPT, DEFAULT_ALLOWED_TYPES)


def test_resolve_type_text_happy_path():
    ct = resolve_type("txt", b"just some text\n", DEFAULT_ALLOWED_TYPES)
    assert ct.startswith("text/plain")


def test_resolve_type_rejects_binary_as_text():
    with pytest.raises(TypeNotAllowed):
        resolve_type("txt", b"\x00\x01\x02binary", DEFAULT_ALLOWED_TYPES)


def test_resolve_type_rejects_unlisted_extension():
    with pytest.raises(TypeNotAllowed):
        resolve_type("exe", PNG_MAGIC, DEFAULT_ALLOWED_TYPES)


def test_content_disposition_neutralizes_header_injection():
    evil = 'evil"\r\nX-Injected: 1; name=../../etc/passwd'
    header = content_disposition(evil)
    # the ASCII filename must contain no CR/LF, quote, semicolon, or path separators
    ascii_part = header.split('filename="', 1)[1].split('"', 1)[0]
    for bad in ["\r", "\n", '"', ";", "/", "\\"]:
        assert bad not in ascii_part
    assert header.startswith("attachment;")
    assert "filename*=UTF-8''" in header
    # the RFC 5987 form percent-encodes the dangerous bytes
    assert "%0D%0A" in header or "%0d%0a" in header


def test_content_disposition_blank_falls_back_to_download():
    assert 'filename="download"' in content_disposition("///")
