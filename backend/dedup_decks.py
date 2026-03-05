"""One-time script to deduplicate decks after user_id removal migration.

Merges decks with the same name by:
1. Finding all groups of decks with identical names
2. Keeping the one with the lowest id (oldest)
3. Reassigning all cards from duplicate decks to the kept deck
4. Updating the kept deck's card_count
5. Deleting the duplicate decks
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import Session, create_engine, select, func, col
from app.models.card import Card
from app.models.deck import Deck

DB_PATH = Path(__file__).parent / "data" / "flashcards.db"
engine = create_engine(f"sqlite:///{DB_PATH}")


def dedup_decks():
    with Session(engine) as session:
        # Find deck names that appear more than once
        dup_query = (
            select(Deck.name, func.count(Deck.id).label("cnt"))
            .group_by(Deck.name)
            .having(func.count(Deck.id) > 1)
        )
        dup_names = session.exec(dup_query).all()

        if not dup_names:
            print("No duplicate decks found.")
            return

        total_removed = 0
        for name, count in dup_names:
            print(f"\nDuplicate deck: '{name}' ({count} copies)")

            # Get all decks with this name, ordered by id
            decks = session.exec(
                select(Deck).where(Deck.name == name).order_by(Deck.id)
            ).all()

            keep = decks[0]
            duplicates = decks[1:]

            for dup in duplicates:
                # Reassign cards from duplicate to kept deck
                cards = session.exec(
                    select(Card).where(Card.deck_id == dup.id)
                ).all()

                moved = 0
                for card in cards:
                    # Check if an identical card (same front) already exists in the kept deck
                    existing = session.exec(
                        select(Card).where(
                            Card.deck_id == keep.id,
                            Card.front == card.front,
                        )
                    ).first()

                    if existing:
                        # Delete the duplicate card
                        session.delete(card)
                    else:
                        # Move card to the kept deck
                        card.deck_id = keep.id
                        session.add(card)
                        moved += 1

                print(f"  Deck id={dup.id}: moved {moved} cards, deleted {len(cards) - moved} duplicate cards")

                # Delete the duplicate deck
                session.delete(dup)
                total_removed += 1

            # Recount cards for the kept deck
            card_count = session.exec(
                select(func.count(Card.id)).where(Card.deck_id == keep.id)
            ).one()
            keep.card_count = card_count
            session.add(keep)
            print(f"  Kept deck id={keep.id}, card_count updated to {card_count}")

        session.commit()
        print(f"\nDone! Removed {total_removed} duplicate decks.")


if __name__ == "__main__":
    dedup_decks()
