"""Test review functionality for debugging 500 errors."""

import sys
import traceback
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, 'c:/code/anki/backend')

from app.database import engine
from sqlmodel import Session, select
from app.models.card import Card
from app.services.review_service import ReviewService

def test_review():
    """Test reviewing a card."""
    session = Session(engine)
    
    # Get a card
    card = session.exec(select(Card).where(Card.user_id == 1).limit(1)).first()
    
    if not card:
        print("No cards found!")
        return
    
    print(f"\n=== Testing Card {card.id} ===")
    print(f"Front: {card.front[:50]}...")
    print(f"State: {card.state}")
    print(f"Due: {card.due}")
    print(f"Stability: {card.stability}")
    print(f"Difficulty: {card.difficulty}")
    print(f"Step: {card.step}")
    print(f"Reps: {card.reps}")
    print(f"Lapses: {card.lapses}")
    print(f"Last Review: {card.last_review}")
    
    # Test review service
    try:
        service = ReviewService(session=session, user_id=1, desired_retention=0.9)
        
        print("\n=== Attempting to review with rating 4 (Easy) ===")
        result = service.review_card(card_id=card.id, rating=4, duration_ms=5000)
        
        print("\n✅ Review successful!")
        print(f"New due: {result['new_due']}")
        print(f"New state: {result['new_state']}")
        print(f"New stability: {result['new_stability']}")
        print(f"New difficulty: {result['new_difficulty']}")
        print(f"Reps: {result['reps']}")
        print(f"Lapses: {result['lapses']}")
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
    
    finally:
        session.close()

if __name__ == "__main__":
    test_review()
