import sys
sys.path.insert(0, 'app')

from database import engine
from sqlmodel import Session
from services.review_service import ReviewService

session = Session(engine)
service = ReviewService(session=session, user_id=1, desired_retention=0.9)

try:
    result = service.review_card(card_id=3, rating=4, duration_ms=5000)
    print(f"✅ Success! New due: {result['new_due']}, state: {result['new_state']}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    session.close()
