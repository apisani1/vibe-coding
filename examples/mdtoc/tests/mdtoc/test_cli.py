"""CLI behavior and exit codes — AC2, AC3, AC4, AC8, AC9, AC11.

Exit-code contract (D6): 0 ok / already-current, 1 stale (only via --check), 2
usage / IO / marker error. These tests assert each path, including that 1 never leaks
into the write path.
"""

import pytest

from mdtoc.cli import main


def test_write_updates_stale_file_exit_zero(run_cli, golden):
    code, file_bytes, _ = run_cli(golden("simple.md"))
    assert code == 0  # a plain stale run writes and exits 0 — never 1
    assert file_bytes.decode("utf-8") == golden("simple.expected.md")


def test_second_run_no_change(run_cli, golden):
    code, first_bytes, path = run_cli(golden("simple.md"))
    assert code == 0
    code2 = main([str(path)])  # run again on the now-current file
    assert code2 == 0
    assert path.read_bytes() == first_bytes  # AC2: idempotent at the file level


def test_check_current_exit_zero_no_write(run_cli, golden):
    code, file_bytes, _ = run_cli(golden("simple.expected.md"), "--check")
    assert code == 0  # AC3
    assert file_bytes.decode("utf-8") == golden("simple.expected.md")  # untouched


def test_check_stale_exit_one_no_write(run_cli, golden):
    code, file_bytes, _ = run_cli(golden("simple.md"), "--check")
    assert code == 1  # AC4
    assert file_bytes.decode("utf-8") == golden("simple.md")  # untouched


def test_max_depth_via_cli(run_cli):
    text = "# T\n\n<!-- toc -->\n<!-- /toc -->\n\n## A\n\n### B\n\n#### C\n"
    _, file_bytes, _ = run_cli(text, "--max-depth", "2")
    out = file_bytes.decode("utf-8")
    assert "- [A](#a)" in out  # AC5 through the CLI
    assert "(#b)" not in out
    assert "(#c)" not in out


def test_missing_markers_exit_two_no_write(run_cli, capsys):
    source = "# No markers here\n\n## A\n"
    code, file_bytes, _ = run_cli(source)
    assert code == 2  # AC8
    assert file_bytes.decode("utf-8") == source  # untouched
    assert "marker" in capsys.readouterr().err.lower()


def test_malformed_markers_exit_two(run_cli):
    code, _, _ = run_cli("<!-- /toc -->\n<!-- toc -->\n")
    assert code == 2


def test_missing_file_exit_two(tmp_path, capsys):
    code = main([str(tmp_path / "does_not_exist.md")])
    assert code == 2  # AC9
    assert capsys.readouterr().err.strip() != ""


def test_help_exits_zero():
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0  # AC11: --help works


def test_write_through_symlink_updates_target_and_preserves_link(tmp_path, golden):
    real = tmp_path / "real.md"
    real.write_text(golden("simple.md"), encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(real)

    code = main([str(link)])

    assert code == 0
    assert link.is_symlink()  # atomic write resolves symlinks; the link is preserved
    assert real.read_text(encoding="utf-8") == golden("simple.expected.md")


def test_invalid_utf8_exits_two_no_traceback(tmp_path, capsys):
    # Non-UTF-8 bytes must map to the documented exit code 2, not a traceback/exit 1.
    target = tmp_path / "bad.md"
    target.write_bytes(b"# T\n\n<!-- toc -->\n<!-- /toc -->\n\xff\xfe")

    code = main([str(target)])

    assert code == 2  # AC9: unreadable content fails cleanly
    assert "bad.md" in capsys.readouterr().err
