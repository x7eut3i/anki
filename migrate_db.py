"""Database migration: add meta_info and quiz_answer_map columns.

Run this script once to add new columns to an existing database.
Safe to run multiple times (checks if columns already exist).

Usage:
    python migrate_db.py                        # Migrate default DB
    python migrate_db.py --db path/to/db.db     # Migrate specific DB
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def get_columns(cursor: sqlite3.Cursor, table: str) -> set[str]:
    """Get existing column names for a table."""
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def migrate(db_path: str):
    """Add new columns to existing database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    migrations = [
        ("cards", "meta_info", "TEXT DEFAULT ''"),
        ("study_sessions", "quiz_answer_map", "TEXT DEFAULT '{}'"),
    ]

    applied = 0
    for table, column, col_type in migrations:
        existing = get_columns(cursor, table)
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f"  ✅ Added {table}.{column}")
            applied += 1
        else:
            print(f"  ⏭  {table}.{column} already exists")

    # Drop deprecated columns
    drop_columns = [
        ("article_analyses", "author"),
    ]
    for table, column in drop_columns:
        existing = get_columns(cursor, table)
        if column in existing:
            sqlite_ver = sqlite3.sqlite_version_info
            if sqlite_ver >= (3, 35, 0):
                try:
                    cursor.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
                    print(f"  ✅ Dropped {table}.{column}")
                    applied += 1
                except Exception as e:
                    print(f"  ⚠️  Could not drop {table}.{column}: {e}")
            else:
                print(f"  ⚠️  SQLite < 3.35.0, cannot drop {table}.{column}")
        else:
            print(f"  ⏭  {table}.{column} already removed")

    conn.commit()
    conn.close()

    print(f"\nMigration complete: {applied} columns added.")


def main():
    parser = argparse.ArgumentParser(description="Database migration")
    parser.add_argument(
        "--db", type=str, default=None,
        help="Database path (default: backend/data/anki.db)",
    )
    args = parser.parse_args()

    db_path = args.db or str(
        Path(__file__).parent / "backend" / "data" / "flashcards.db"
    )

    if not Path(db_path).exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    print(f"Migrating: {db_path}")
    migrate(db_path)


if __name__ == "__main__":
    main()
