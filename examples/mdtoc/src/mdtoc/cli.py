"""Command-line interface: argument parsing, file IO, and exit-code mapping.

All filesystem access and process-exit logic lives here; the pure core
(:func:`mdtoc.document.render`) never touches the disk. Exit codes: ``0`` success or
already-current, ``1`` stale (only under ``--check``), ``2`` usage / IO / marker error.
"""

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path

from mdtoc.document import MdtocError, render


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically: temp file in the same dir + ``os.replace``.

    A truncate-then-write can corrupt the user's file if the process dies mid-write;
    an atomic rename guarantees the original is either fully intact or fully replaced.
    Symlinks are resolved first so the real file is updated in place (preserving the
    "edit the file the link points to" behavior) and its mode is carried over.
    """
    target = Path(os.path.realpath(path))
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        try:
            os.chmod(tmp_name, stat.S_IMODE(os.stat(target).st_mode))
        except OSError:
            pass  # best-effort mode preservation; not worth failing the write
        os.replace(tmp_name, target)
        replaced = True
    finally:
        # Any exit before the rename (OSError, KeyboardInterrupt, MemoryError, …) must
        # not leave an orphaned temp file; the original is untouched until os.replace.
        if not replaced:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the ``mdtoc`` command."""
    parser = argparse.ArgumentParser(
        prog="mdtoc",
        description="Inject or update a linked Markdown table of contents between "
        "<!-- toc --> and <!-- /toc --> markers.",
    )
    parser.add_argument("path", help="Markdown file to update in place.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the TOC is stale; do not modify the file.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=6,
        metavar="N",
        help="Deepest heading level to include (default: 6).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse args, render or check the target file, and return the exit code (0/1/2)."""
    args = build_parser().parse_args(argv)
    path = Path(args.path)

    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"mdtoc: cannot read {args.path}: {exc}", file=sys.stderr)
        return 2

    try:
        updated = render(original, args.max_depth)
    except MdtocError as exc:
        print(f"mdtoc: {args.path}: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if updated != original:
            print(f"mdtoc: {args.path}: TOC is out of date", file=sys.stderr)
            return 1
        return 0

    if updated != original:
        try:
            _atomic_write(path, updated)
        except OSError as exc:
            print(f"mdtoc: cannot write {args.path}: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
