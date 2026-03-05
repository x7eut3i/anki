#!/usr/bin/env python3
"""
Database migration: Apply schema simplification.

Changes:
  - Add 'distractors' column (TEXT, default '')
  - Migrate data from card_type+choices+correct_answer → back+distractors
  - Drop old columns (card_type, choices, correct_answer)

SQLite doesn't support DROP COLUMN in older versions, so we recreate the table.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

# Default database path
BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BACKEND_DIR / "data" / "flashcards.db"


def migrate(db_path: str | None = None):
    db_file = Path(db_path) if db_path else DEFAULT_DB
    if not db_file.exists():
        print(f"❌ Database not found: {db_file}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if migration is needed
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(cards)").fetchall()]

    if "distractors" in columns and "card_type" not in columns:
        print("✅ Database already migrated, nothing to do.")
        conn.close()
        return

    print(f"📦 Migrating database: {db_file}")
    print(f"   Current columns: {columns}")

    # Step 1: Add distractors column if it doesn't exist
    if "distractors" not in columns:
        print("   Adding 'distractors' column...")
        cursor.execute("ALTER TABLE cards ADD COLUMN distractors VARCHAR DEFAULT ''")
        conn.commit()

    # Step 2: Migrate data from old format to new format
    print("   Migrating card data...")
    rows = cursor.execute(
        "SELECT id, card_type, front, back, choices, correct_answer FROM cards"
    ).fetchall()

    migrated = 0
    for row in rows:
        card_id = row["id"]
        card_type = row["card_type"] or ""
        back = row["back"] or ""
        choices_raw = row["choices"] or ""
        correct_answer = row["correct_answer"] or ""

        # Parse choices
        choices = []
        if choices_raw:
            try:
                choices = json.loads(choices_raw)
            except (json.JSONDecodeError, TypeError):
                choices = []

        new_back = back
        distractors = []

        if card_type == "choice" and choices:
            if correct_answer and len(correct_answer) == 1 and correct_answer.isalpha():
                idx = ord(correct_answer.upper()) - ord('A')
                if 0 <= idx < len(choices):
                    raw_text = choices[idx]
                    new_back = re.sub(r'^[A-Z]\.\s*', '', raw_text)
                    for i, ch in enumerate(choices):
                        if i != idx:
                            distractors.append(re.sub(r'^[A-Z]\.\s*', '', ch))
            elif back and back not in ("A", "B", "C", "D"):
                new_back = back
                for ch in choices:
                    text = re.sub(r'^[A-Z]\.\s*', '', ch)
                    if text != new_back:
                        distractors.append(text)
        elif card_type == "true_false":
            if not back or back in ("对", "错", "正确", "错误"):
                new_back = correct_answer or back

        distractors_str = json.dumps(distractors, ensure_ascii=False) if distractors else ""

        cursor.execute(
            "UPDATE cards SET back = ?, distractors = ? WHERE id = ?",
            (new_back, distractors_str, card_id),
        )
        migrated += 1

    conn.commit()
    print(f"   ✅ Migrated {migrated} cards")

    # Step 3: Drop old columns by recreating the table
    # SQLite >= 3.35.0 supports DROP COLUMN
    sqlite_version = sqlite3.sqlite_version_info
    print(f"   SQLite version: {sqlite3.sqlite_version}")

    if sqlite_version >= (3, 35, 0):
        print("   Dropping old columns (card_type, choices, correct_answer)...")
        for col in ["card_type", "choices", "correct_answer"]:
            if col in columns:
                try:
                    cursor.execute(f"ALTER TABLE cards DROP COLUMN {col}")
                except Exception as e:
                    print(f"   ⚠️  Could not drop {col}: {e}")
        conn.commit()
    else:
        print("   ⚠️  SQLite < 3.35.0, cannot DROP COLUMN. Old columns remain but are unused.")

    conn.close()
    print("✅ Migration complete!")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    migrate(db_path)
