"""The ``shorturl`` command-line admin.

Subcommands operate directly on the SQLite file (the same file the API serves from), so
``list`` / ``expire`` / ``delete`` and the HTTP service share one source of truth. The
database path comes from the environment via :class:`Config`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import (
    Callable,
    Iterator,
    Sequence,
)
from contextlib import contextmanager

from waitress import serve as waitress_serve  # type: ignore[import-untyped]

from . import (
    codes,
    db,
)
from .api import create_app
from .config import Config

Handler = Callable[[argparse.Namespace, Config], int]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``shorturl`` console script. Returns a process exit code."""
    args = _build_parser().parse_args(argv)
    config = Config.from_env()
    handler: Handler = args.handler
    return handler(args, config)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shorturl", description="URL shortener admin and server.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="list all codes with status and click counts")
    list_p.set_defaults(handler=_cmd_list)

    expire_p = sub.add_parser("expire", help="deactivate a code so it stops redirecting")
    expire_p.add_argument("code")
    expire_p.set_defaults(handler=_cmd_expire)

    delete_p = sub.add_parser("delete", help="delete a code and its click history")
    delete_p.add_argument("code")
    delete_p.set_defaults(handler=_cmd_delete)

    serve_p = sub.add_parser("serve", help="run the HTTP API server (host/port/key from env)")
    serve_p.set_defaults(handler=_cmd_serve)

    return parser


def _cmd_serve(_args: argparse.Namespace, config: Config) -> int:
    """Run the API under waitress. Fails closed if no API key is configured."""
    config.require_api_key()
    app = create_app(config)
    print(f"shorturl serving on http://{config.host}:{config.port}", file=sys.stderr)
    waitress_serve(app, host=config.host, port=config.port)
    return 0


def _cmd_list(_args: argparse.Namespace, config: Config) -> int:
    with _connection(config) as conn:
        rows = db.list_codes(conn)
    _print_codes(rows)
    return 0


def _cmd_expire(args: argparse.Namespace, config: Config) -> int:
    with _connection(config) as conn:
        ok = db.expire_code(conn, args.code)
    if not ok:
        return _not_found(args.code)
    print(f"expired {args.code}")
    return 0


def _cmd_delete(args: argparse.Namespace, config: Config) -> int:
    with _connection(config) as conn:
        ok = db.delete_code(conn, args.code)
    if not ok:
        return _not_found(args.code)
    print(f"deleted {args.code}")
    return 0


@contextmanager
def _connection(config: Config) -> Iterator[sqlite3.Connection]:
    """Open a schema-initialized connection and close it on exit."""
    conn = db.connect(config.db_path)
    try:
        db.init_schema(conn)
        yield conn
    finally:
        conn.close()


def _not_found(code: str) -> int:
    print(f"error: no such code: {code}", file=sys.stderr)
    return 1


def _print_codes(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("no codes")
        return
    now = codes.utcnow()
    header = f"{'CODE':<20} {'STATUS':<12} {'CLICKS':>6}  {'CREATED':<26} {'EXPIRES':<26} TARGET"
    print(header)
    for row in rows:
        state = codes.status(row["active"], row["expires_at"], now)
        expires = row["expires_at"] or "-"
        print(
            f"{row['code']:<20} {state:<12} {row['click_count']:>6}  "
            f"{row['created_at']:<26} {expires:<26} {row['target_url']}"
        )
