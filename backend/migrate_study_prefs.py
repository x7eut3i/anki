"""Add study_question_mode and study_custom_ratio columns to users table."""
import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent / "data" / "flashcards.db"
conn = sqlite3.connect(str(db))
cursor = conn.cursor()
cols = [row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()]
print("Current user columns:", cols)

if "study_question_mode" not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN study_question_mode VARCHAR DEFAULT 'custom'")
    print("Added study_question_mode")
else:
    print("study_question_mode already exists")

if "study_custom_ratio" not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN study_custom_ratio INTEGER DEFAULT 60")
    print("Added study_custom_ratio")
else:
    print("study_custom_ratio already exists")

conn.commit()
conn.close()
print("Done!")
