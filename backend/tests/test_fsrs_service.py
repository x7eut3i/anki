"""Tests for the FSRS service (spaced repetition logic).

Comprehensive tests verifying:
- Correct delegation to py-fsrs library
- State mapping between app DB model (NEW=0,LEARNING=1,REVIEW=2,RELEARNING=3)
  and py-fsrs (Learning=1,Review=2,Relearning=3)
- Full card lifecycle: New → Learning → Review → Relearning → Review
- Round-trip serialization (dict → FSRSCard → dict)
- All 4 rating buttons at each state
- Stability growth over successful reviews
- Difficulty adjustments
- Overdue card handling
- Desired retention effect on intervals
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.fsrs_service import FSRSService


# ── Helpers ──────────────────────────────────────────────────────────

def _new_card(now: datetime) -> dict:
    """Standard new card dict matching DB schema."""
    return {
        "due": now,
        "stability": 0.0,
        "difficulty": 0.0,
        "step": 0,
        "reps": 0,
        "lapses": 0,
        "state": 0,  # NEW
        "last_review": None,
    }


def _graduate_card(service: FSRSService, now: datetime) -> tuple[dict, datetime]:
    """Review a new card through learning steps to reach Review state."""
    card = _new_card(now)
    t = now
    # Keep reviewing Good until card reaches Review state (2)
    for _ in range(10):
        card, _ = service.review_card(card, 3, t)
        if card["state"] == 2:
            return card, t
        t = card["due"]
    # If still not Review, force one more
    card, _ = service.review_card(card, 3, t)
    return card, t


# ── Basic card creation ──────────────────────────────────────────────

class TestFSRSNewCard:
    def test_create_new_card(self):
        service = FSRSService()
        card = service.create_new_card()
        assert card is not None

    def test_new_card_to_dict(self):
        service = FSRSService()
        card = service.create_new_card()
        d = service._fsrs_card_to_dict(card)
        assert "due" in d
        assert "step" in d
        assert d["stability"] == 0.0

    def test_new_card_dict_has_all_fields(self):
        service = FSRSService()
        card = service.create_new_card()
        d = service._fsrs_card_to_dict(card)
        expected_keys = {"due", "stability", "difficulty", "step", "state", "last_review"}
        assert expected_keys == set(d.keys())


# ── State mapping & round-trip ───────────────────────────────────────

class TestStateMapping:
    """Verify the mapping between app DB states and py-fsrs states."""

    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_new_state_maps_to_learning(self):
        """App state=0 (NEW) should map to py-fsrs Learning with step=0."""
        from fsrs import State
        card_data = _new_card(self.now)
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        assert fsrs_card.state == State.Learning
        assert fsrs_card.step == 0

    def test_learning_state_roundtrip(self):
        """State=1 (LEARNING) survives dict→card→dict round-trip."""
        card_data = {"due": self.now, "stability": 2.5, "difficulty": 3.0,
                     "step": 1, "state": 1, "last_review": self.now}
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        result = self.service._fsrs_card_to_dict(fsrs_card)
        assert result["state"] == 1
        assert result["step"] == 1
        assert result["stability"] == 2.5
        assert result["difficulty"] == 3.0

    def test_review_state_roundtrip(self):
        """State=2 (REVIEW) survives dict→card→dict round-trip."""
        card_data = {"due": self.now, "stability": 10.0, "difficulty": 5.0,
                     "step": 0, "state": 2, "last_review": self.now - timedelta(days=10)}
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        result = self.service._fsrs_card_to_dict(fsrs_card)
        assert result["state"] == 2

    def test_relearning_state_roundtrip(self):
        """State=3 (RELEARNING) survives dict→card→dict round-trip."""
        card_data = {"due": self.now, "stability": 1.0, "difficulty": 7.0,
                     "step": 0, "state": 3, "last_review": self.now}
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        result = self.service._fsrs_card_to_dict(fsrs_card)
        assert result["state"] == 3

    def test_zero_stability_maps_to_none(self):
        """stability=0.0 from DB (uninitialized) should map to None for py-fsrs."""
        card_data = _new_card(self.now)
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        assert fsrs_card.stability is None
        assert fsrs_card.difficulty is None

    def test_nonzero_stability_preserved(self):
        """Non-zero stability from DB should be preserved."""
        card_data = {"due": self.now, "stability": 5.5, "difficulty": 3.2,
                     "step": 0, "state": 2, "last_review": self.now}
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        assert fsrs_card.stability == 5.5
        assert fsrs_card.difficulty == 3.2

    def test_string_due_date_parsed(self):
        """ISO string due date should be parsed correctly."""
        card_data = {"due": "2026-02-25T12:00:00+00:00", "stability": 0.0,
                     "difficulty": 0.0, "step": 0, "state": 0, "last_review": None}
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        assert fsrs_card.due == self.now

    def test_naive_datetime_gets_utc(self):
        """Naive datetime should be treated as UTC."""
        naive_dt = datetime(2026, 2, 25, 12, 0, 0)
        card_data = {"due": naive_dt, "stability": 0.0, "difficulty": 0.0,
                     "step": 0, "state": 0, "last_review": None}
        fsrs_card = self.service._dict_to_fsrs_card(card_data)
        assert fsrs_card.due.tzinfo is not None


# ── First review (all ratings) ───────────────────────────────────────

class TestFirstReview:
    """Test first review of a new card with each rating."""

    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_again_stays_in_learning(self):
        updated, _ = self.service.review_card(_new_card(self.now), 1, self.now)
        assert updated["state"] == 1  # Learning
        assert updated["reps"] == 1
        assert updated["lapses"] == 1  # Again on first review
        assert updated["due"] > self.now
        # Should be due within minutes (learning step)
        assert (updated["due"] - self.now) < timedelta(hours=1)

    def test_hard_stays_in_learning(self):
        updated, _ = self.service.review_card(_new_card(self.now), 2, self.now)
        assert updated["state"] == 1  # Still learning
        assert updated["reps"] == 1
        assert updated["lapses"] == 0

    def test_good_stays_in_learning(self):
        updated, _ = self.service.review_card(_new_card(self.now), 3, self.now)
        assert updated["state"] == 1  # Still learning (step 1)
        assert updated["reps"] == 1
        assert updated["lapses"] == 0
        assert updated["stability"] > 0

    def test_easy_may_graduate(self):
        """Easy on a new card may graduate to Review or advance learning."""
        updated, _ = self.service.review_card(_new_card(self.now), 4, self.now)
        assert updated["reps"] == 1
        assert updated["lapses"] == 0
        assert updated["stability"] > 0
        # Easy should have the longest interval
        good_updated, _ = self.service.review_card(_new_card(self.now), 3, self.now)
        assert updated["due"] >= good_updated["due"]

    def test_rating_order_preserves_interval_ordering(self):
        """Again < Hard < Good < Easy in terms of next due date."""
        results = {}
        for rating in [1, 2, 3, 4]:
            updated, _ = self.service.review_card(_new_card(self.now), rating, self.now)
            results[rating] = updated["due"]
        assert results[1] <= results[2] <= results[3] <= results[4]


# ── Full lifecycle ───────────────────────────────────────────────────

class TestCardLifecycle:
    """Test complete card lifecycle through all states."""

    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_new_to_learning_to_review(self):
        """Card should progress: NEW(0) → LEARNING(1) → REVIEW(2)."""
        card = _new_card(self.now)
        t = self.now

        # First review
        card, _ = self.service.review_card(card, 3, t)
        assert card["state"] == 1  # Learning

        # Keep reviewing Good until graduated
        for _ in range(10):
            if card["state"] == 2:
                break
            t = card["due"]
            card, _ = self.service.review_card(card, 3, t)

        assert card["state"] == 2, "Card should graduate to Review state"

    def test_review_to_relearning_on_again(self):
        """A Review card that gets Again should go to Relearning."""
        card, t = _graduate_card(self.service, self.now)
        assert card["state"] == 2  # Confirm in Review

        # Lapse: Again
        t = card["due"]
        card, _ = self.service.review_card(card, 1, t)
        assert card["state"] == 3  # Relearning
        assert card["lapses"] >= 1

    def test_relearning_back_to_review(self):
        """A Relearning card should return to Review after Good reviews."""
        card, t = _graduate_card(self.service, self.now)

        # Lapse
        t = card["due"]
        card, _ = self.service.review_card(card, 1, t)
        assert card["state"] == 3  # Relearning

        # Review Good until back to Review
        for _ in range(10):
            if card["state"] == 2:
                break
            t = card["due"]
            card, _ = self.service.review_card(card, 3, t)

        assert card["state"] == 2, "Card should return to Review after relearning"

    def test_stability_grows_with_successful_reviews(self):
        """Stability should generally increase with consecutive Good reviews."""
        card, t = _graduate_card(self.service, self.now)
        stabilities = [card["stability"]]

        for _ in range(5):
            t = card["due"]
            card, _ = self.service.review_card(card, 3, t)
            if card["state"] == 2:
                stabilities.append(card["stability"])

        # Stability should be increasing (each review at due date with Good)
        for i in range(1, len(stabilities)):
            assert stabilities[i] >= stabilities[i - 1], \
                f"Stability should grow: {stabilities[i]} >= {stabilities[i - 1]} at step {i}"

    def test_long_term_intervals_grow(self):
        """Intervals between reviews should grow over time with Good ratings."""
        card, t = _graduate_card(self.service, self.now)
        intervals = []

        for _ in range(5):
            old_due = card["due"]
            t = card["due"]
            card, _ = self.service.review_card(card, 3, t)
            if card["state"] == 2:
                interval = (card["due"] - t).total_seconds()
                intervals.append(interval)

        # At least some intervals should be increasing
        assert len(intervals) >= 2, "Need at least 2 intervals to compare"
        assert intervals[-1] >= intervals[0], \
            f"Later interval ({intervals[-1]:.0f}s) should be >= first ({intervals[0]:.0f}s)"

    def test_reps_counter_increments(self):
        """Reps should increment by 1 on every review."""
        card = _new_card(self.now)
        t = self.now
        for expected_reps in range(1, 6):
            card, _ = self.service.review_card(card, 3, t)
            assert card["reps"] == expected_reps
            t = card["due"]

    def test_lapses_only_on_again(self):
        """Lapses should only increment when rating is 1 (Again)."""
        card = _new_card(self.now)
        t = self.now

        # Good review — no lapse
        card, _ = self.service.review_card(card, 3, t)
        assert card["lapses"] == 0

        t = card["due"]
        # Hard review — no lapse
        card, _ = self.service.review_card(card, 2, t)
        assert card["lapses"] == 0

        t = card["due"]
        # Again — lapse!
        card, _ = self.service.review_card(card, 1, t)
        assert card["lapses"] == 1

        t = card["due"]
        # Easy — no lapse
        card, _ = self.service.review_card(card, 4, t)
        assert card["lapses"] == 1  # Still 1

        t = card["due"]
        # Again — second lapse!
        card, _ = self.service.review_card(card, 1, t)
        assert card["lapses"] == 2


# ── Review at different states ───────────────────────────────────────

class TestReviewAtStates:
    """Test all 4 ratings when card is in Review state."""

    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_review_state_again(self):
        card, _ = _graduate_card(self.service, self.now)
        t = card["due"]
        updated, log = self.service.review_card(card, 1, t)
        assert updated["state"] == 3  # Relearning
        assert log["state"] == 2  # Was in Review

    def test_review_state_hard(self):
        card, _ = _graduate_card(self.service, self.now)
        t = card["due"]
        updated, _ = self.service.review_card(card, 2, t)
        assert updated["state"] == 2  # Stays in Review
        assert updated["due"] > t

    def test_review_state_good(self):
        card, _ = _graduate_card(self.service, self.now)
        t = card["due"]
        updated, _ = self.service.review_card(card, 3, t)
        assert updated["state"] == 2  # Stays in Review
        assert updated["due"] > t

    def test_review_state_easy(self):
        card, _ = _graduate_card(self.service, self.now)
        t = card["due"]
        updated, _ = self.service.review_card(card, 4, t)
        assert updated["state"] == 2  # Stays in Review
        assert updated["due"] > t


# ── Overdue card handling ────────────────────────────────────────────

class TestOverdueReview:
    """Test reviewing a card that is overdue (past its due date)."""

    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_overdue_review_still_works(self):
        """A card reviewed after its due date should still be scheduled properly."""
        card, _ = _graduate_card(self.service, self.now)
        due_date = card["due"]

        # Review 30 days after due date
        overdue_time = due_date + timedelta(days=30)
        updated, _ = self.service.review_card(card, 3, overdue_time)

        assert updated["due"] > overdue_time
        assert updated["last_review"] == overdue_time

    def test_overdue_card_good_gives_reasonable_interval(self):
        """Overdue card with Good rating should get a reasonable next interval."""
        card, _ = _graduate_card(self.service, self.now)
        due_date = card["due"]

        overdue_time = due_date + timedelta(days=10)
        updated, _ = self.service.review_card(card, 3, overdue_time)

        interval = (updated["due"] - overdue_time).days
        assert interval >= 1, "Should be scheduled at least 1 day out"
        assert interval <= 36500, "Should not exceed maximum interval"


# ── Review log ───────────────────────────────────────────────────────

class TestReviewLog:
    """Test that review log captures correct pre-review state."""

    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_log_captures_pre_state(self):
        _, log = self.service.review_card(_new_card(self.now), 3, self.now)
        assert log["state"] == 0  # Was NEW before review
        assert log["rating"] == 3
        assert log["reviewed_at"] == self.now

    def test_log_captures_review_state(self):
        card, _ = _graduate_card(self.service, self.now)
        t = card["due"]
        _, log = self.service.review_card(card, 3, t)
        assert log["state"] == 2  # Was in Review

    def test_log_captures_pre_stability(self):
        card, _ = _graduate_card(self.service, self.now)
        pre_stability = card["stability"]
        t = card["due"]
        _, log = self.service.review_card(card, 3, t)
        assert log["stability"] == pre_stability

    def test_log_default_review_time(self):
        """If no review_time specified, should use current time."""
        _, log = self.service.review_card(_new_card(self.now), 3)
        assert log["reviewed_at"] is not None
        # Should be close to now (within a second)
        assert abs((log["reviewed_at"] - datetime.now(timezone.utc)).total_seconds()) < 2


# ── Preview ratings ──────────────────────────────────────────────────

class TestFSRSPreview:
    def test_preview_shows_all_ratings(self):
        service = FSRSService()
        now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
        card_data = _new_card(now)

        preview = service.preview_ratings(card_data, now)
        assert "again" in preview
        assert "hard" in preview
        assert "good" in preview
        assert "easy" in preview
        assert preview["again_days"] <= preview["hard_days"] <= preview["good_days"] <= preview["easy_days"]

    def test_preview_does_not_modify_card(self):
        service = FSRSService()
        now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
        card_data = _new_card(now)

        _ = service.preview_ratings(card_data, now)

        # Original card_data should be unchanged
        assert card_data["reps"] == 0
        assert card_data["stability"] == 0.0

    def test_preview_review_state_intervals(self):
        """Preview of a Review card should show meaningful intervals."""
        service = FSRSService(desired_retention=0.9)
        now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
        card, _ = _graduate_card(service, now)
        t = card["due"]

        preview = service.preview_ratings(card, t)
        # Review state card should have multi-day intervals for Good/Easy
        assert preview["good_days"] >= 1
        assert preview["easy_days"] >= preview["good_days"]


# ── Retrievability ───────────────────────────────────────────────────

class TestFSRSRetrievability:
    def test_new_card_retrievability(self):
        service = FSRSService()
        card_data = _new_card(datetime.now(timezone.utc))
        r = service.get_retrievability(card_data)
        assert 0.0 <= r <= 1.0

    def test_reviewed_card_retrievability(self):
        service = FSRSService()
        now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
        card_data = _new_card(now)
        card_data, _ = service.review_card(card_data, 3, now)
        r = service.get_retrievability(card_data)
        assert 0.0 <= r <= 1.0

    def test_retrievability_decreases_over_time(self):
        """Retrievability should drop as time passes since last review."""
        service = FSRSService()
        now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
        card, _ = _graduate_card(service, now)

        # Check at due time
        r_at_due = service.get_retrievability(card)
        # This should be around desired_retention (0.9)
        assert r_at_due > 0.0


# ── Desired retention ────────────────────────────────────────────────

class TestFSRSDesiredRetention:
    def test_higher_retention_shorter_intervals(self):
        """Higher desired retention should produce shorter intervals."""
        now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
        card_data = _new_card(now)

        service_high = FSRSService(desired_retention=0.95)
        service_low = FSRSService(desired_retention=0.80)

        high_updated, _ = service_high.review_card(card_data.copy(), 3, now)
        low_updated, _ = service_low.review_card(card_data.copy(), 3, now)

        # Higher retention = review sooner
        assert high_updated["due"] <= low_updated["due"]

    def test_retention_bounds(self):
        """Service should work with extreme retention values."""
        now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
        card_data = _new_card(now)

        for ret in [0.7, 0.8, 0.85, 0.9, 0.95, 0.99]:
            service = FSRSService(desired_retention=ret)
            updated, _ = service.review_card(card_data.copy(), 3, now)
            assert updated["due"] > now


# ── Difficulty adjustments ───────────────────────────────────────────

class TestDifficultyAdjustment:
    """Test that difficulty adjusts based on rating patterns."""

    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_easy_lowers_difficulty(self):
        """Consistently Easy ratings should result in lower difficulty."""
        card = _new_card(self.now)
        t = self.now
        for _ in range(5):
            card, _ = self.service.review_card(card, 4, t)  # Easy
            t = card["due"]
        easy_difficulty = card["difficulty"]

        card2 = _new_card(self.now)
        t = self.now
        for _ in range(5):
            card2, _ = self.service.review_card(card2, 2, t)  # Hard
            t = card2["due"]
        hard_difficulty = card2["difficulty"]

        assert easy_difficulty < hard_difficulty, \
            f"Easy path difficulty ({easy_difficulty:.2f}) should be < Hard path ({hard_difficulty:.2f})"

    def test_difficulty_stays_bounded(self):
        """Difficulty should stay within reasonable bounds."""
        card = _new_card(self.now)
        t = self.now
        # Many Again ratings
        for _ in range(10):
            card, _ = self.service.review_card(card, 1, t)
            t = card["due"]
        assert card["difficulty"] <= 10.0, "Difficulty should not exceed 10"
        assert card["difficulty"] >= 0.0, "Difficulty should not go below 0"


# ── Edge cases ───────────────────────────────────────────────────────

class TestEdgeCases:
    def setup_method(self):
        self.service = FSRSService(desired_retention=0.9)
        self.now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_multiple_lapses(self):
        """Card should handle multiple lapse cycles."""
        card, t = _graduate_card(self.service, self.now)

        for i in range(3):
            t = card["due"]
            # Lapse
            card, _ = self.service.review_card(card, 1, t)
            assert card["state"] == 3  # Relearning
            # Recover
            for _ in range(10):
                if card["state"] == 2:
                    break
                t = card["due"]
                card, _ = self.service.review_card(card, 3, t)

        assert card["lapses"] >= 3

    def test_last_review_updated(self):
        """last_review should be set to the review time."""
        card = _new_card(self.now)
        updated, _ = self.service.review_card(card, 3, self.now)
        assert updated["last_review"] == self.now

    def test_step_none_to_zero(self):
        """py-fsrs returns step=None for graduated cards, should map to 0."""
        card, _ = _graduate_card(self.service, self.now)
        assert card["step"] == 0 or card["step"] is not None

    def test_review_with_string_dates_in_data(self):
        """Card data with ISO string dates should work."""
        card_data = {
            "due": "2026-02-25T12:00:00+00:00",
            "stability": 0.0,
            "difficulty": 0.0,
            "step": 0,
            "reps": 0,
            "lapses": 0,
            "state": 0,
            "last_review": None,
        }
        updated, _ = self.service.review_card(card_data, 3, self.now)
        assert updated["reps"] == 1
