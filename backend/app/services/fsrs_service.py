"""FSRS-6 spaced repetition service wrapping py-fsrs."""

import logging
from copy import deepcopy
from datetime import datetime, timezone

from fsrs import Card as FSRSCard, Scheduler, Rating, State

logger = logging.getLogger(__name__)


class FSRSService:
    """Wraps py-fsrs Scheduler for card scheduling."""

    def __init__(self, desired_retention: float = 0.9):
        self.scheduler = Scheduler(
            desired_retention=desired_retention,
            enable_fuzzing=True,
            maximum_interval=36500,
        )

    _RATING_MAP = {
        1: Rating.Again,
        2: Rating.Hard,
        3: Rating.Good,
        4: Rating.Easy,
    }

    def create_new_card(self) -> FSRSCard:
        """Create a new FSRS card."""
        return FSRSCard()

    def review_card(
        self,
        card_data: dict,
        rating: int,
        review_time: datetime | None = None,
        review_duration: int | None = None,
    ) -> tuple[dict, dict]:
        """
        Review a card and return updated card data + review log.

        Args:
            card_data: Dict with FSRS fields from DB card (must include card_id).
            rating: 1=Again, 2=Hard, 3=Good, 4=Easy
            review_time: When the review happened (default: now)
            review_duration: Time spent reviewing in milliseconds (forwarded to
                py-fsrs for Optimizer.compute_optimal_retention support).

        Returns:
            (updated_card_dict, review_log_dict)
        """
        if rating not in self._RATING_MAP:
            raise ValueError(
                f"Invalid rating {rating}. Must be 1-4 (Again=1, Hard=2, Good=3, Easy=4)"
            )

        if review_time is None:
            review_time = datetime.now(timezone.utc)

        # Build FSRS card from DB fields
        fsrs_card = self._dict_to_fsrs_card(card_data)
        fsrs_rating = self._RATING_MAP[rating]

        # Capture pre-review state for log
        pre_state = card_data.get("state", 0)
        pre_due = card_data.get("due", review_time)
        if isinstance(pre_due, str):
            pre_due = datetime.fromisoformat(pre_due)
        pre_stability = card_data.get("stability", 0.0) or 0.0
        pre_difficulty = card_data.get("difficulty", 0.0) or 0.0

        last_review = card_data.get("last_review")
        if isinstance(last_review, str):
            last_review = datetime.fromisoformat(last_review)

        # Perform the review — forward review_duration to py-fsrs
        new_card, _fsrs_log = self.scheduler.review_card(
            fsrs_card, fsrs_rating, review_time,
            review_duration=review_duration,
        )

        # Convert back to dict for DB storage
        updated = self._fsrs_card_to_dict(new_card)

        # Track reps and lapses at the app level
        # (py-fsrs does not track these; they are app-layer counters)
        old_reps = card_data.get("reps", 0)
        old_lapses = card_data.get("lapses", 0)
        updated["reps"] = old_reps + 1
        if rating == 1:  # Again
            updated["lapses"] = old_lapses + 1
        else:
            updated["lapses"] = old_lapses

        # elapsed_days: actual days since last review (0 for first review)
        elapsed_days = 0
        if last_review is not None:
            if isinstance(last_review, datetime):
                lr = last_review
                if lr.tzinfo is None:
                    lr = lr.replace(tzinfo=timezone.utc)
                elapsed_days = max(0, (review_time - lr).days)

        # scheduled_days: the interval that was scheduled (due - last_review)
        scheduled_days = 0
        if last_review is not None and pre_due is not None:
            if isinstance(pre_due, datetime) and isinstance(last_review, datetime):
                pd = pre_due
                lr = last_review
                if pd.tzinfo is None:
                    pd = pd.replace(tzinfo=timezone.utc)
                if lr.tzinfo is None:
                    lr = lr.replace(tzinfo=timezone.utc)
                scheduled_days = max(0, (pd - lr).days)

        log = {
            "rating": rating,
            "state": pre_state,
            "due": pre_due,
            "stability": pre_stability,
            "difficulty": pre_difficulty,
            "elapsed_days": elapsed_days,
            "scheduled_days": scheduled_days,
            "reviewed_at": review_time,
        }

        return updated, log

    def preview_ratings(
        self, card_data: dict, review_time: datetime | None = None
    ) -> dict:
        """
        Preview what happens for each rating without applying changes.

        Returns dict with keys: again, hard, good, easy (each is a due datetime).
        """
        if review_time is None:
            review_time = datetime.now(timezone.utc)

        fsrs_card = self._dict_to_fsrs_card(card_data)

        result = {}
        for rating_int, rating_enum in [
            (1, Rating.Again),
            (2, Rating.Hard),
            (3, Rating.Good),
            (4, Rating.Easy),
        ]:
            preview_card = deepcopy(fsrs_card)
            new_card, _ = self.scheduler.review_card(
                preview_card, rating_enum, review_time
            )
            label = {1: "again", 2: "hard", 3: "good", 4: "easy"}[rating_int]
            result[label] = new_card.due
            result[f"{label}_days"] = max(0, (new_card.due - review_time).days)

        return result

    def get_retrievability(self, card_data: dict) -> float:
        """Get current retrievability (probability of recall) for a card."""
        fsrs_card = self._dict_to_fsrs_card(card_data)
        try:
            return self.scheduler.get_card_retrievability(fsrs_card)
        except Exception:
            logger.warning("Failed to calculate retrievability", exc_info=True)
            return 0.0

    def _dict_to_fsrs_card(self, data: dict) -> FSRSCard:
        """Convert DB card dict to FSRS Card object.

        Expects ``data`` to contain at least ``card_id`` (int) so that the
        FSRSCard constructor does not auto-generate an id (which triggers a
        1 ms ``time.sleep`` in py-fsrs).
        """
        # Pass card_id to avoid py-fsrs auto-id (time.sleep(0.001))
        card_id = data.get("card_id")
        card = FSRSCard(card_id=card_id) if card_id is not None else FSRSCard()

        if data.get("due"):
            due = data["due"]
            if isinstance(due, str):
                due = datetime.fromisoformat(due)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            card.due = due

        if data.get("stability") is not None:
            # py-fsrs uses None for new cards; 0.0 from DB means uninitialized
            card.stability = data["stability"] if data["stability"] != 0.0 else None
        if data.get("difficulty") is not None:
            card.difficulty = data["difficulty"] if data["difficulty"] != 0.0 else None
        if data.get("step") is not None:
            card.step = data["step"]

        # Map our state values to FSRS State enum
        # Our DB: NEW=0, LEARNING=1, REVIEW=2, RELEARNING=3
        # py-fsrs: Learning=1, Review=2, Relearning=3 (no NEW state)
        # NEW cards are treated as Learning with step=0.  The first review
        # will apply the configured learning_steps (default: 1 min, 10 min).
        state_val = data.get("state", 0)
        if isinstance(state_val, int):
            if state_val == 0:
                card.state = State.Learning
                card.step = 0
            else:
                card.state = State(state_val)
        else:
            card.state = State(int(state_val))

        if data.get("last_review"):
            lr = data["last_review"]
            if isinstance(lr, str):
                lr = datetime.fromisoformat(lr)
            if lr.tzinfo is None:
                lr = lr.replace(tzinfo=timezone.utc)
            card.last_review = lr

        return card

    def _fsrs_card_to_dict(self, card: FSRSCard) -> dict:
        """Convert FSRS Card object to dict for DB storage."""
        return {
            "due": card.due,
            "stability": card.stability if card.stability is not None else 0.0,
            "difficulty": card.difficulty if card.difficulty is not None else 0.0,
            "step": card.step if card.step is not None else 0,
            "state": card.state.value if hasattr(card.state, "value") else int(card.state),
            "last_review": card.last_review,
        }
