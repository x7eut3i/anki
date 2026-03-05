#!/usr/bin/env python3
"""
Smart Content Importer for Anki Flashcard App

Imports JSON content files from the content/ directory into the database.
Features:
  - Auto-matches category by filename (e.g., 01_成语.json → category "成语")
  - Auto-creates a default deck per category if none exists
  - Smart deduplication: identifies existing cards by (front text + category_id)
  - Upsert mode: updates existing cards or inserts new ones
  - Dry-run mode: preview changes without modifying the database
  - Detailed import report

Usage:
  python import_content.py                    # Import all JSON files
  python import_content.py --dry-run          # Preview without importing
  python import_content.py --file 01_成语.json  # Import a single file
  python import_content.py --force-update     # Overwrite existing cards
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add the backend directory to Python path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import Session, select, create_engine, SQLModel
from app.config import get_settings
from app.models.card import Card
from app.models.category import Category, DEFAULT_CATEGORIES
from app.models.deck import Deck
from app.models.user import User


# ─── Helpers ────────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize text for comparison: strip whitespace, normalize unicode."""
    if not text:
        return ""
    # Strip leading/trailing whitespace
    text = text.strip()
    # Collapse multiple whitespace into single space
    text = re.sub(r'\s+', ' ', text)
    return text


def cards_are_same(existing: Card, new_data: dict) -> bool:
    """
    Check if two cards are the same by comparing front text within the same category.
    This is the primary dedup key: (normalized_front, category_id).
    """
    return normalize_text(existing.front) == normalize_text(new_data.get("front", ""))


def card_needs_update(existing: Card, new_data: dict) -> bool:
    """
    Check if an existing card's content differs from new data.
    Compares: back, explanation, distractors, tags.
    """
    fields_to_compare = [
        ("back", "back"),
        ("explanation", "explanation"),
        ("tags", "tags"),
        ("source", "source"),
        ("source_date", "source_date"),
    ]

    for db_field, json_field in fields_to_compare:
        db_val = normalize_text(getattr(existing, db_field, "") or "")
        new_val = normalize_text(str(new_data.get(json_field, "") or ""))
        if db_val != new_val:
            return True

    # Compare distractors (JSON array)
    existing_distractors = existing.distractors or ""
    new_distractors = new_data.get("distractors", [])
    if isinstance(new_distractors, list):
        new_distractors_str = json.dumps(new_distractors, ensure_ascii=False)
    else:
        new_distractors_str = str(new_distractors) if new_distractors else ""

    if normalize_text(existing_distractors) != normalize_text(new_distractors_str):
        return True

    return False


def extract_category_name(filename: str) -> str:
    """
    Extract category name from filename.
    e.g., '01_成语.json' → '成语'
          '05_法律常识.json' → '法律常识'
    """
    stem = Path(filename).stem  # e.g., '01_成语'
    # Remove leading number and underscore
    match = re.match(r'^\d+[_\-](.+)$', stem)
    if match:
        return match.group(1)
    return stem


def convert_legacy_card(card_data: dict) -> dict:
    """
    Convert legacy card format (card_type + choices + correct_answer) to new format
    (back as answer text + distractors as wrong answers).

    Legacy: card_type, choices (JSON string), correct_answer (letter), back (letter)
    New:    back (answer text), distractors (list of wrong answers)
    """
    card_type = card_data.get("card_type", "")
    choices_raw = card_data.get("choices", "")
    correct_answer = card_data.get("correct_answer", "")
    back = card_data.get("back", "")

    # If card already has "distractors" field, it's new format — skip conversion
    if "distractors" in card_data:
        # Clean up any leftover legacy fields
        card_data.pop("card_type", None)
        card_data.pop("choices", None)
        card_data.pop("correct_answer", None)
        return card_data

    # Parse choices from JSON string
    choices = []
    if choices_raw:
        if isinstance(choices_raw, str):
            try:
                choices = json.loads(choices_raw)
            except (json.JSONDecodeError, TypeError):
                choices = []
        elif isinstance(choices_raw, list):
            choices = choices_raw

    if card_type == "choice" and choices:
        answer_text = back
        distractors = []

        if correct_answer and len(correct_answer) == 1 and correct_answer.isalpha():
            idx = ord(correct_answer.upper()) - ord('A')
            if 0 <= idx < len(choices):
                raw_text = choices[idx]
                answer_text = re.sub(r'^[A-Z]\.\s*', '', raw_text)
                for i, ch in enumerate(choices):
                    if i != idx:
                        distractors.append(re.sub(r'^[A-Z]\.\s*', '', ch))
        elif back and back not in ("A", "B", "C", "D"):
            answer_text = back
            for ch in choices:
                text = re.sub(r'^[A-Z]\.\s*', '', ch)
                if text != answer_text:
                    distractors.append(text)

        card_data["back"] = answer_text
        card_data["distractors"] = distractors
    elif card_type == "true_false":
        if not back or back in ("对", "错", "正确", "错误"):
            card_data["back"] = correct_answer or back
        card_data["distractors"] = []
    else:
        card_data["distractors"] = []

    # Clean up legacy fields
    card_data.pop("card_type", None)
    card_data.pop("choices", None)
    card_data.pop("correct_answer", None)

    return card_data


# ─── Main Import Logic ──────────────────────────────────────────────────────

def ensure_categories(session: Session) -> dict[str, Category]:
    """Ensure all default categories exist in the database. Returns name→Category map."""
    categories = {}

    for cat_data in DEFAULT_CATEGORIES:
        existing = session.exec(
            select(Category).where(Category.name == cat_data["name"])
        ).first()

        if existing:
            categories[cat_data["name"]] = existing
        else:
            cat = Category(**cat_data)
            session.add(cat)
            session.flush()
            categories[cat_data["name"]] = cat
            print(f"  📁 Created category: {cat_data['name']}")

    return categories


def ensure_deck(session: Session, category: Category, user_id: int) -> Deck:
    """Ensure a default deck exists for this category and user."""
    deck = session.exec(
        select(Deck).where(
            Deck.category_id == category.id,
            Deck.user_id == user_id,
        )
    ).first()

    if not deck:
        deck = Deck(
            name=f"{category.icon} {category.name}",
            description=category.description,
            user_id=user_id,
            category_id=category.id,
            is_public=False,
        )
        session.add(deck)
        session.flush()
        print(f"  📦 Created deck: {deck.name}")

    return deck


def ensure_user(session: Session) -> User:
    """Get the first user, or create a default admin user."""
    user = session.exec(select(User)).first()
    if not user:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        user = User(
            username="admin",
            email="admin@example.com",
            hashed_password=pwd_context.hash("admin123"),
            is_admin=True,
        )
        session.add(user)
        session.flush()
        print("  👤 Created default admin user (admin / admin123)")
    return user


def import_file(
    session: Session,
    filepath: Path,
    categories: dict[str, Category],
    user: User,
    dry_run: bool = False,
    force_update: bool = False,
) -> dict:
    """
    Import a single JSON content file into the database.

    Returns a stats dict: {inserted, updated, skipped, errors, total}
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0, "total": 0}

    # Load JSON
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            cards_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  ❌ Error reading {filepath.name}: {e}")
        stats["errors"] = 1
        return stats

    if not isinstance(cards_data, list):
        print(f"  ❌ {filepath.name}: Expected JSON array, got {type(cards_data).__name__}")
        stats["errors"] = 1
        return stats

    stats["total"] = len(cards_data)

    # Match category
    cat_name = extract_category_name(filepath.name)
    category = categories.get(cat_name)
    if not category:
        print(f"  ⚠️  No category found for '{cat_name}' (file: {filepath.name})")
        print(f"      Available: {', '.join(categories.keys())}")
        stats["errors"] = len(cards_data)
        return stats

    # Get or create deck
    deck = ensure_deck(session, category, user.id)

    # Load existing cards for this category+user (for dedup)
    existing_cards = session.exec(
        select(Card).where(
            Card.category_id == category.id,
            Card.user_id == user.id,
        )
    ).all()

    # Build a lookup index: normalized_front → Card
    existing_index: dict[str, Card] = {}
    for card in existing_cards:
        key = normalize_text(card.front)
        existing_index[key] = card

    # Process each card
    for i, card_data in enumerate(cards_data, 1):
        # Convert legacy format (card_type + choices + correct_answer) to new format
        card_data = convert_legacy_card(card_data)

        front = card_data.get("front", "").strip()
        if not front:
            print(f"    ⚠️  Card #{i}: Empty front text, skipping")
            stats["errors"] += 1
            continue

        lookup_key = normalize_text(front)
        existing_card = existing_index.get(lookup_key)

        if existing_card:
            # Card exists — check if it needs updating
            if force_update or card_needs_update(existing_card, card_data):
                if dry_run:
                    print(f"    🔄 Would update: {front[:50]}...")
                else:
                    # Update the existing card's content fields (preserve FSRS state)
                    existing_card.back = card_data.get("back", existing_card.back)
                    existing_card.explanation = card_data.get("explanation", existing_card.explanation)
                    existing_card.tags = card_data.get("tags", existing_card.tags)
                    existing_card.source = card_data.get("source", existing_card.source)
                    existing_card.source_date = card_data.get("source_date", existing_card.source_date)

                    distractors = card_data.get("distractors", [])
                    if isinstance(distractors, list):
                        existing_card.distractors = json.dumps(distractors, ensure_ascii=False)
                    elif distractors:
                        existing_card.distractors = str(distractors)

                    existing_card.updated_at = datetime.now(timezone.utc)
                    session.add(existing_card)

                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        else:
            # New card — insert
            distractors = card_data.get("distractors", [])
            if isinstance(distractors, list):
                distractors_str = json.dumps(distractors, ensure_ascii=False)
            else:
                distractors_str = str(distractors) if distractors else ""

            if dry_run:
                print(f"    ➕ Would insert: {front[:50]}...")
            else:
                # Process meta_info
                meta_info = card_data.get("meta_info", "")
                if isinstance(meta_info, dict):
                    meta_info = json.dumps(meta_info, ensure_ascii=False)

                new_card = Card(
                    deck_id=deck.id,
                    user_id=user.id,
                    category_id=category.id,
                    front=front,
                    back=card_data.get("back", ""),
                    explanation=card_data.get("explanation", ""),
                    distractors=distractors_str,
                    tags=card_data.get("tags", ""),
                    meta_info=meta_info,
                    source=card_data.get("source", ""),
                    source_date=card_data.get("source_date", ""),
                    is_ai_generated=False,
                )
                session.add(new_card)

            stats["inserted"] += 1

    return stats


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import flashcard content into the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python import_content.py                      Import all content files
  python import_content.py --dry-run            Preview changes
  python import_content.py --file 01_成语.json   Import one file
  python import_content.py --force-update       Overwrite existing cards
  python import_content.py --db path/to/db      Use a specific database
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be imported without making changes",
    )
    parser.add_argument(
        "--force-update", action="store_true",
        help="Force update even if content hasn't changed",
    )
    parser.add_argument(
        "--file", type=str, default=None,
        help="Import a specific JSON file (filename only, not full path)",
    )
    parser.add_argument(
        "--content-dir", type=str, default=None,
        help="Path to content directory (default: ./content relative to this script)",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to SQLite database file (default: from settings/env)",
    )

    args = parser.parse_args()

    # Determine content directory
    content_dir = Path(args.content_dir) if args.content_dir else SCRIPT_DIR
    if not content_dir.exists():
        print(f"❌ Content directory not found: {content_dir}")
        sys.exit(1)

    # Set up database
    if args.db:
        db_url = f"sqlite:///{args.db}"
    else:
        # Default: backend/data/flashcards.db relative to project root
        default_db = BACKEND_DIR / "data" / "flashcards.db"
        settings = get_settings()
        settings_db_path = settings.database_url.replace("sqlite:///", "")
        # If settings path is relative, resolve from backend dir
        if not os.path.isabs(settings_db_path):
            resolved = BACKEND_DIR / settings_db_path
        else:
            resolved = Path(settings_db_path)
        if resolved.exists():
            db_url = f"sqlite:///{resolved}"
        elif default_db.exists():
            db_url = f"sqlite:///{default_db}"
        else:
            # Create at resolved location
            resolved.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{resolved}"

    engine = create_engine(
        db_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Ensure tables exist
    SQLModel.metadata.create_all(engine)

    # Gather JSON files
    if args.file:
        json_files = [content_dir / args.file]
        if not json_files[0].exists():
            print(f"❌ File not found: {json_files[0]}")
            sys.exit(1)
    else:
        json_files = sorted(content_dir.glob("*.json"))
        if not json_files:
            print(f"❌ No JSON files found in {content_dir}")
            sys.exit(1)

    # Print header
    mode = "DRY RUN" if args.dry_run else "IMPORT"
    print(f"\n{'='*60}")
    print(f"  📥 Flashcard Content Importer — {mode}")
    print(f"  📂 Content: {content_dir}")
    print(f"  💾 Database: {db_url}")
    print(f"{'='*60}\n")

    # Run import
    total_stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0, "total": 0}

    with Session(engine) as session:
        # Ensure categories and user exist
        print("🔧 Setting up...")
        categories = ensure_categories(session)
        user = ensure_user(session)

        if not args.dry_run:
            session.commit()

        print(f"\n📂 Processing {len(json_files)} file(s)...\n")

        for filepath in json_files:
            print(f"  📄 {filepath.name}")
            stats = import_file(
                session=session,
                filepath=filepath,
                categories=categories,
                user=user,
                dry_run=args.dry_run,
                force_update=args.force_update,
            )

            # Accumulate stats
            for key in total_stats:
                total_stats[key] += stats[key]

            # Print per-file summary
            parts = []
            if stats["inserted"]:
                parts.append(f"✅ {stats['inserted']} new")
            if stats["updated"]:
                parts.append(f"🔄 {stats['updated']} updated")
            if stats["skipped"]:
                parts.append(f"⏭️  {stats['skipped']} unchanged")
            if stats["errors"]:
                parts.append(f"❌ {stats['errors']} errors")
            print(f"     → {', '.join(parts) or 'empty file'}")
            print()

        # Update deck card counts
        if not args.dry_run:
            decks = session.exec(select(Deck).where(Deck.user_id == user.id)).all()
            for deck in decks:
                count = len(session.exec(
                    select(Card).where(Card.deck_id == deck.id)
                ).all())
                deck.card_count = count
                session.add(deck)

            session.commit()

    # Print summary
    print(f"{'='*60}")
    print(f"  📊 Import Summary")
    print(f"{'='*60}")
    print(f"  Total cards processed : {total_stats['total']}")
    print(f"  ✅ Inserted (new)     : {total_stats['inserted']}")
    print(f"  🔄 Updated            : {total_stats['updated']}")
    print(f"  ⏭️  Skipped (same)     : {total_stats['skipped']}")
    print(f"  ❌ Errors             : {total_stats['errors']}")
    print(f"{'='*60}")

    if args.dry_run:
        print("\n  ℹ️  This was a dry run. No changes were made.")
        print("     Run without --dry-run to apply changes.\n")
    else:
        print("\n  ✨ Import complete!\n")


if __name__ == "__main__":
    main()
