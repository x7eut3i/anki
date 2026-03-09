#!/usr/bin/env python3
"""Add quiz_questions and quiz_user_answers columns to study_sessions."""

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "flashcards.db"

conn = sqlite3.connect(str(DB))
cols = [r[1] for r in conn.execute("PRAGMA table_info(study_sessions)").fetchall()]
print("Existing columns:", cols)

if "quiz_questions" not in cols:
    conn.execute("ALTER TABLE study_sessions ADD COLUMN quiz_questions TEXT DEFAULT '[]'")
    print("Added quiz_questions")
else:
    print("quiz_questions already exists")

if "quiz_user_answers" not in cols:
    conn.execute("ALTER TABLE study_sessions ADD COLUMN quiz_user_answers TEXT DEFAULT '{}'")
    print("Added quiz_user_answers")
else:
    print("quiz_user_answers already exists")

conn.commit()
conn.close()
print("Done")
