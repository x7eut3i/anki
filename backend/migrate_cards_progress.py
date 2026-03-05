"""Migration script: Split Card table into shared content + per-user FSRS progress.

This script:
1. Creates the user_card_progress table
2. Copies FSRS scheduling data from cards to user_card_progress
3. Removes user_id and FSRS columns from cards table
4. Removes user_id from decks table

Run:  python -m backend.migrate_cards_progress
  or: cd backend && python migrate_cards_progress.py
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

DB_PATH = backend_dir / "data" / "flashcards.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}, nothing to migrate.")
        print("The new schema will be created automatically on next startup.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = OFF")
    cursor = conn.cursor()

    try:
        # ── 1. Create user_card_progress table ────────────────────────
        print("Step 1: Creating user_card_progress table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_card_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                card_id INTEGER NOT NULL REFERENCES cards(id),
                due TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                stability REAL NOT NULL DEFAULT 0.0,
                difficulty REAL NOT NULL DEFAULT 0.0,
                step INTEGER NOT NULL DEFAULT 0,
                reps INTEGER NOT NULL DEFAULT 0,
                lapses INTEGER NOT NULL DEFAULT 0,
                state INTEGER NOT NULL DEFAULT 0,
                last_review TIMESTAMP,
                is_suspended BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, card_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_user_card_progress_user_id
            ON user_card_progress(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_user_card_progress_card_id
            ON user_card_progress(card_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_user_card_progress_due
            ON user_card_progress(due)
        """)
        print("  ✅ user_card_progress table created")

        # ── 2. Copy FSRS data from cards to user_card_progress ────────
        print("Step 2: Copying FSRS data from cards to user_card_progress...")

        # Check if cards table has the old columns
        cursor.execute("PRAGMA table_info(cards)")
        columns = {row[1] for row in cursor.fetchall()}

        if "user_id" in columns and "due" in columns:
            cursor.execute("""
                INSERT OR IGNORE INTO user_card_progress
                    (user_id, card_id, due, stability, difficulty, step,
                     reps, lapses, state, last_review, is_suspended,
                     created_at, updated_at)
                SELECT
                    user_id, id, due, stability, difficulty, step,
                    reps, lapses, state, last_review, is_suspended,
                    created_at, updated_at
                FROM cards
                WHERE user_id IS NOT NULL
            """)
            copied = cursor.rowcount
            print(f"  ✅ Copied {copied} card progress records")
        else:
            print("  ⏭ Cards table already migrated (no FSRS columns), skipping copy")

        # ── 3. Recreate cards table without user_id and FSRS columns ──
        print("Step 3: Recreating cards table without user_id/FSRS columns...")

        if "user_id" in columns:
            cursor.execute("""
                CREATE TABLE cards_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deck_id INTEGER NOT NULL REFERENCES decks(id),
                    category_id INTEGER REFERENCES categories(id),
                    front VARCHAR(5000) NOT NULL,
                    back VARCHAR(5000) NOT NULL,
                    explanation VARCHAR(5000) NOT NULL DEFAULT '',
                    distractors TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    meta_info TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    source_date TEXT NOT NULL DEFAULT '',
                    expires_at TIMESTAMP,
                    is_ai_generated BOOLEAN NOT NULL DEFAULT 0,
                    ai_review_status VARCHAR NOT NULL DEFAULT 'approved',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO cards_new
                    (id, deck_id, category_id, front, back, explanation,
                     distractors, tags, meta_info, source, source_date,
                     expires_at, is_ai_generated, ai_review_status,
                     created_at, updated_at)
                SELECT
                    id, deck_id, category_id, front, back, explanation,
                    distractors, tags, meta_info, source, source_date,
                    expires_at, is_ai_generated, ai_review_status,
                    created_at, updated_at
                FROM cards
            """)
            cursor.execute("DROP TABLE cards")
            cursor.execute("ALTER TABLE cards_new RENAME TO cards")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_cards_deck_id ON cards(deck_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_cards_category_id ON cards(category_id)")
            print("  ✅ Cards table recreated without user_id/FSRS columns")
        else:
            print("  ⏭ Cards table already clean, skipping")

        # ── 4. Recreate decks table without user_id ───────────────────
        print("Step 4: Recreating decks table without user_id...")

        cursor.execute("PRAGMA table_info(decks)")
        deck_columns = {row[1] for row in cursor.fetchall()}

        if "user_id" in deck_columns:
            cursor.execute("""
                CREATE TABLE decks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(200) NOT NULL,
                    description VARCHAR(1000) NOT NULL DEFAULT '',
                    category_id INTEGER REFERENCES categories(id),
                    is_public BOOLEAN NOT NULL DEFAULT 0,
                    card_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                INSERT INTO decks_new
                    (id, name, description, category_id, is_public,
                     card_count, created_at, updated_at)
                SELECT
                    id, name, description, category_id, is_public,
                    card_count, created_at, updated_at
                FROM decks
            """)
            cursor.execute("DROP TABLE decks")
            cursor.execute("ALTER TABLE decks_new RENAME TO decks")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_decks_name ON decks(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_decks_category_id ON decks(category_id)")
            print("  ✅ Decks table recreated without user_id")
        else:
            print("  ⏭ Decks table already clean, skipping")

        conn.commit()
        print("\n✅ Migration completed successfully!")
        print("   - user_card_progress table: created")
        print("   - cards table: user_id & FSRS columns removed")
        print("   - decks table: user_id removed")
        print("   - All cards are now shared across users")
        print("   - FSRS progress is tracked per-user in user_card_progress")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


if __name__ == "__main__":
    migrate()
