"""Local operator command for hiding a declaration without deleting its evidence.

Run on the API host as the account allowed to write its store. There is no network command, public write endpoint,
scorer startup, or shared operator credential. The filesystem's store permissions are the authorization boundary.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from .store import HIDE_REASONS, Store


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # Neither malformed arguments nor database errors may echo visitor text into operator receipts.
        self.exit(2, "Invalid arguments; use --help.\n")


def main(argv=None) -> int:
    parser = SafeParser(prog="python -m app.door.moderation", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    hide = commands.add_parser("hide", help="Hide one existing declaration event in public responses")
    hide.add_argument("--store", type=Path, required=True, help="Explicit existing Door SQLite file")
    hide.add_argument("--seq", type=int, required=True, help="Declaration event sequence number")
    hide.add_argument("--reason", choices=HIDE_REASONS, required=True)
    args = parser.parse_args(argv)
    try:
        store = Store(args.store, existing_only=True)
        result = store.hide_declaration(args.seq, args.reason, now=time.time())
    except ValueError as error:
        code = str(error)
        if code not in {"invalid_seq", "invalid_reason", "invalid_time", "not_declaration", "invalid_hide_record"}:
            code = "store_unavailable"
        print(json.dumps({"status": "refused", "error": code}))
        return 1
    except (OSError, sqlite3.Error):
        print(json.dumps({"status": "refused", "error": "store_unavailable"}))
        return 1
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
