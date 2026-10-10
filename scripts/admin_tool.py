"""Administrator helper.

  python scripts/admin_tool.py hash-password     print a hash for ADMIN_PASSWORD_HASH (Render)
  python scripts/admin_tool.py create-admin      store an admin in data/admin.json (local use)
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BASE_DIR, build_config  # noqa: E402
from quiz_app.services import auth_service  # noqa: E402
from quiz_app.storage import Database  # noqa: E402


def read_password() -> str:
    first = getpass.getpass("Password (min %d characters): " % auth_service.MIN_PASSWORD_LENGTH)
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match.")
    return first


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hash-password")
    create = sub.add_parser("create-admin")
    create.add_argument("--username", default="admin")
    args = parser.parse_args()

    try:
        if args.command == "hash-password":
            print(auth_service.hash_password(read_password()))
        else:
            config = build_config({"SECRET_KEY": "cli-tool-not-used-for-sessions"})
            db = Database(config["DATA_DIR"], config["SAMPLE_QUESTIONS_PATH"])
            auth_service.create_admin(db, args.username, read_password())
            print(f"Administrator '{args.username}' saved to {Path(config['DATA_DIR']) / 'admin.json'}")
    except ValueError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    main()
