"""DESTRUCTIVE: drop every app table and re-run Alembic to head.

Use only in development. Production must `alembic upgrade head` against a DB
that already matches the previous migration — never drop tables.

Usage:
    python scripts/reset_db.py --yes
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from sqlmodel import SQLModel

import app.models  # noqa: F401 — register tables
from app.database import engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation flag — without this, the script refuses to run.",
    )
    args = parser.parse_args()

    print(f"Target: {engine.url}")
    if not args.yes:
        print("Refusing to run without --yes. This drops every app table.")
        return 1

    print("Dropping all app tables...")
    SQLModel.metadata.drop_all(bind=engine)

    print("Resetting Alembic version table...")
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

    print("Running alembic upgrade head...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], check=False
    )
    if result.returncode != 0:
        print("alembic upgrade failed; see output above.")
        return result.returncode

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
