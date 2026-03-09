"""Review service: handles card reviews, due card queries, and study stats."""

import json
from datetime import datetime, timezone, timedelta

from sqlmodel import Session, select, func, col, text
from sqlalchemy import or_

from app.models.card import Card, CardState
from app.models.user_card_progress import UserCardProgress
from app.models.review_log import ReviewLog
from app.models.study_session import StudySession
from app.models.category import Category
from app.services.fsrs_service import FSRSService


class ReviewService:
    def __init__(self, session: Session, user_id: int, desired_retention: float = 0.9):
        self.session = session
        self.user_id = user_id
        self.fsrs = FSRSService(desired_retention=desired_retention)

    # ── Helper: get or create progress record ─────────────────────────

    def _get_or_create_progress(self, card_id: int) -> UserCardProgress:
        """Get existing progress or create a new one for this user+card."""
        progress = self.session.exec(
            select(UserCardProgress).where(
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.card_id == card_id,
            )
        ).first()
        if not progress:
            progress = UserCardProgress(
                user_id=self.user_id,
                card_id=card_id,
            )
            self.session.add(progress)
            self.session.commit()
            self.session.refresh(progress)
        return progress

    def get_due_cards(
        self,
        category_ids: list[int] | None = None,
        deck_id: int | None = None,
        deck_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        exclude_ai_decks: bool = False,
        limit: int = 50,
    ) -> dict:
        """Get cards due for review, prioritized by state and due date.

        Cards without a UserCardProgress record are treated as NEW and due now.
        """
        from app.models.deck import Deck
        now = datetime.now(timezone.utc)

        # LEFT JOIN Card with UserCardProgress for this user
        query = (
            select(Card, UserCardProgress)
            .outerjoin(
                UserCardProgress,
                (UserCardProgress.card_id == Card.id)
                & (UserCardProgress.user_id == self.user_id),
            )
            .where(
                (Card.expires_at == None) | (Card.expires_at > now),
                # Not suspended (NULL progress = not suspended)
                or_(
                    UserCardProgress.id == None,
                    UserCardProgress.is_suspended == False,
                ),
                # Due: no progress (new) or progress.due <= now
                or_(
                    UserCardProgress.id == None,
                    UserCardProgress.due <= now,
                ),
            )
        )

        # Category/deck filtering — use OR when both are specified (mix mode)
        if category_ids and deck_ids:
            query = query.where(
                or_(
                    col(Card.category_id).in_(category_ids),
                    col(Card.deck_id).in_(deck_ids),
                )
            )
        elif category_ids:
            query = query.where(col(Card.category_id).in_(category_ids))
            if exclude_ai_decks:
                query = query.outerjoin(Deck, Card.deck_id == Deck.id).where(
                    col(Deck.name).not_like("AI-%") | (Card.deck_id == None)  # noqa: E711
                )
        elif deck_ids:
            query = query.where(col(Card.deck_id).in_(deck_ids))
        elif deck_id is not None:
            query = query.where(Card.deck_id == deck_id)
        if tag_ids:
            from app.models.tag import CardTag
            tagged_ids = self.session.exec(
                select(CardTag.card_id).where(col(CardTag.tag_id).in_(tag_ids))
            ).all()
            if tagged_ids:
                query = query.where(col(Card.id).in_(tagged_ids))
            else:
                # No cards match these tags
                return {"cards": [], "total_due": 0, "new_count": 0, "review_count": 0, "relearning_count": 0}

        # Priority: Relearning > Learning > New > Review
        query = query.order_by(
            text("""
                CASE
                    WHEN user_card_progress.state IS NULL THEN 2
                    WHEN user_card_progress.state = 3 THEN 0
                    WHEN user_card_progress.state = 1 THEN 1
                    WHEN user_card_progress.state = 0 THEN 2
                    WHEN user_card_progress.state = 2 THEN 3
                END
            """),
            text("COALESCE(user_card_progress.due, '1970-01-01')"),
        ).limit(limit)

        rows = self.session.exec(query).all()

        # Build response: merge card + progress into dict-like objects
        cards_with_progress = []
        for card, progress in rows:
            cards_with_progress.append(
                self._merge_card_progress(card, progress)
            )

        # Count by state
        count_query = (
            select(
                func.coalesce(UserCardProgress.state, CardState.NEW),
                func.count(),
            )
            .select_from(Card)
            .outerjoin(
                UserCardProgress,
                (UserCardProgress.card_id == Card.id)
                & (UserCardProgress.user_id == self.user_id),
            )
            .where(
                (Card.expires_at == None) | (Card.expires_at > now),
                or_(
                    UserCardProgress.id == None,
                    UserCardProgress.is_suspended == False,
                ),
                or_(
                    UserCardProgress.id == None,
                    UserCardProgress.due <= now,
                ),
            )
        )
        # Category/deck count filtering — must match main query logic
        if category_ids and deck_ids:
            count_query = count_query.where(
                or_(
                    col(Card.category_id).in_(category_ids),
                    col(Card.deck_id).in_(deck_ids),
                )
            )
        elif category_ids:
            count_query = count_query.where(col(Card.category_id).in_(category_ids))
            if exclude_ai_decks:
                from app.models.deck import Deck as DeckModel
                count_query = count_query.outerjoin(DeckModel, Card.deck_id == DeckModel.id).where(
                    col(DeckModel.name).not_like("AI-%") | (Card.deck_id == None)  # noqa: E711
                )
        elif deck_ids:
            count_query = count_query.where(col(Card.deck_id).in_(deck_ids))
        elif deck_id is not None:
            count_query = count_query.where(Card.deck_id == deck_id)
        count_query = count_query.group_by(
            func.coalesce(UserCardProgress.state, CardState.NEW)
        )
        counts = {row[0]: row[1] for row in self.session.exec(count_query).all()}

        return {
            "cards": cards_with_progress,
            "total_due": sum(counts.values()),
            "new_count": counts.get(CardState.NEW, 0),
            "review_count": counts.get(CardState.REVIEW, 0),
            "relearning_count": counts.get(CardState.RELEARNING, 0) + counts.get(
                CardState.LEARNING, 0
            ),
        }

    def review_card(self, card_id: int, rating: int, duration_ms: int = 0) -> dict:
        """Submit a review for a card. Returns updated card info."""
        card = self.session.get(Card, card_id)
        if not card:
            raise ValueError("Card not found")

        now = datetime.now(timezone.utc)

        # Get or create per-user progress
        progress = self._get_or_create_progress(card_id)

        # Build FSRS card data from progress
        card_data = {
            "due": progress.due if progress.due else now,
            "stability": progress.stability if progress.stability is not None else 0.0,
            "difficulty": progress.difficulty if progress.difficulty is not None else 0.0,
            "step": progress.step if progress.step is not None else 0,
            "reps": progress.reps if progress.reps is not None else 0,
            "lapses": progress.lapses if progress.lapses is not None else 0,
            "state": progress.state if progress.state is not None else 0,
            "last_review": progress.last_review if progress.last_review else None,
        }

        # Run FSRS
        updated, log_data = self.fsrs.review_card(card_data, rating, now)

        # Save review log
        review_log = ReviewLog(
            card_id=card_id,
            user_id=self.user_id,
            rating=rating,
            state=log_data["state"],
            due=log_data["due"],
            stability=log_data["stability"],
            difficulty=log_data["difficulty"],
            elapsed_days=log_data.get("elapsed_days", 0),
            scheduled_days=log_data.get("scheduled_days", 0),
            review_duration_ms=duration_ms,
            reviewed_at=now,
        )
        self.session.add(review_log)

        # Update progress
        progress.due = updated["due"]
        progress.stability = updated["stability"]
        progress.difficulty = updated["difficulty"]
        progress.step = updated.get("step", 0) if updated.get("step") is not None else 0
        progress.reps = updated["reps"]
        progress.lapses = updated["lapses"]
        progress.state = updated["state"]
        progress.last_review = updated["last_review"]
        progress.updated_at = now

        self.session.add(progress)
        self.session.commit()
        self.session.refresh(progress)

        return {
            "card_id": card.id,
            "new_due": progress.due,
            "new_stability": progress.stability,
            "new_difficulty": progress.difficulty,
            "new_state": progress.state,
            "reps": progress.reps,
            "lapses": progress.lapses,
        }

    def preview_ratings(self, card_id: int) -> dict:
        """Preview next due dates for each rating option."""
        card = self.session.get(Card, card_id)
        if not card:
            raise ValueError("Card not found")

        progress = self.session.exec(
            select(UserCardProgress).where(
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.card_id == card_id,
            )
        ).first()

        now = datetime.now(timezone.utc)
        card_data = {
            "due": progress.due if progress else now,
            "stability": progress.stability if progress else 0.0,
            "difficulty": progress.difficulty if progress else 0.0,
            "step": progress.step if progress else 0,
            "reps": progress.reps if progress else 0,
            "lapses": progress.lapses if progress else 0,
            "state": progress.state if progress else 0,
            "last_review": progress.last_review if progress else None,
        }
        return self.fsrs.preview_ratings(card_data)

    def create_study_session(
        self,
        mode: str = "review",
        category_ids: list[int] | None = None,
        deck_id: int | None = None,
        deck_ids: list[int] | None = None,
        exclude_ai_decks: bool = False,
        card_limit: int = 50,
        quiz_time_limit: int = 0,
        question_mode: str = "custom",
        custom_ratio: int = 60,
    ) -> StudySession:
        """Create a new study session with selected cards.

        Automatically closes any existing incomplete non-quiz sessions.
        """
        # Auto-close any existing incomplete non-quiz sessions for this user
        stale_sessions = self.session.exec(
            select(StudySession).where(
                StudySession.user_id == self.user_id,
                StudySession.is_completed == False,
                StudySession.mode != "quiz",
            )
        ).all()
        for ss in stale_sessions:
            ss.is_completed = True
            ss.finished_at = datetime.now(timezone.utc)
            self.session.add(ss)
        if stale_sessions:
            self.session.commit()

        due_result = self.get_due_cards(
            category_ids=category_ids,
            deck_id=deck_id,
            deck_ids=deck_ids,
            exclude_ai_decks=exclude_ai_decks,
            limit=card_limit,
        )
        card_ids = [c["id"] for c in due_result["cards"]]

        session_obj = StudySession(
            user_id=self.user_id,
            mode=mode,
            category_ids=",".join(str(c) for c in (category_ids or [])),
            deck_id=deck_id,
            total_cards=len(card_ids),
            remaining_card_ids=json.dumps(card_ids),
            quiz_time_limit=quiz_time_limit,
            question_mode=question_mode,
            custom_ratio=custom_ratio,
        )
        self.session.add(session_obj)
        self.session.commit()
        self.session.refresh(session_obj)
        return session_obj

    def get_active_session(self, exclude_modes: list[str] | None = None) -> StudySession | None:
        """Get the most recent incomplete study session for recovery.

        Auto-closes sessions older than 24 hours.
        """
        # Auto-close stale sessions (> 24h old)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        stale = self.session.exec(
            select(StudySession).where(
                StudySession.user_id == self.user_id,
                StudySession.is_completed == False,
                StudySession.started_at < cutoff,
            )
        ).all()
        for ss in stale:
            ss.is_completed = True
            ss.finished_at = datetime.now(timezone.utc)
            self.session.add(ss)
        if stale:
            self.session.commit()

        query = (
            select(StudySession)
            .where(
                StudySession.user_id == self.user_id,
                StudySession.is_completed == False,
            )
        )
        if exclude_modes:
            for mode in exclude_modes:
                query = query.where(StudySession.mode != mode)
        query = query.order_by(StudySession.started_at.desc())
        return self.session.exec(query).first()

    def update_session_progress(
        self, session_id: int, card_id: int, is_correct: bool
    ) -> StudySession:
        """Update session after reviewing a card."""
        study_session = self.session.get(StudySession, session_id)
        if not study_session or study_session.user_id != self.user_id:
            raise ValueError("Session not found")

        study_session.cards_reviewed += 1
        if is_correct:
            study_session.cards_correct += 1
        else:
            study_session.cards_again += 1

        # Remove card from remaining
        remaining = json.loads(study_session.remaining_card_ids)
        if card_id in remaining:
            remaining.remove(card_id)
        study_session.remaining_card_ids = json.dumps(remaining)

        if not remaining:
            study_session.is_completed = True
            study_session.finished_at = datetime.now(timezone.utc)

        self.session.add(study_session)
        self.session.commit()
        self.session.refresh(study_session)
        return study_session

    def get_study_stats(self, tz=None) -> dict:
        """Get comprehensive study statistics.

        When *tz* (a ZoneInfo instance) is provided, "today" boundaries
        are computed in the user's local timezone.
        """
        now = datetime.now(timezone.utc)

        if tz:
            now_local = datetime.now(tz)
            today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start = today_start_local.astimezone(timezone.utc)
        else:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Total cards (shared — all cards)
        total = self.session.exec(
            select(func.count()).select_from(Card)
        ).one()

        # Due today (cards with progress due now + new cards without progress)
        due_with_progress = self.session.exec(
            select(func.count()).where(
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.is_suspended == False,
                UserCardProgress.due <= now,
            )
        ).one()

        # New cards (no progress record for this user)
        cards_with_progress = self.session.exec(
            select(func.count()).where(
                UserCardProgress.user_id == self.user_id,
            )
        ).one()
        approved_cards = self.session.exec(
            select(func.count()).where(
                (Card.expires_at == None) | (Card.expires_at > now),
            )
        ).one()
        new_cards = max(0, approved_cards - cards_with_progress)
        due_today = due_with_progress + new_cards

        # Reviewed today
        reviewed_today = self.session.exec(
            select(func.count()).where(
                ReviewLog.user_id == self.user_id,
                ReviewLog.reviewed_at >= today_start,
            )
        ).one()

        # Time studied today
        time_today = self.session.exec(
            select(func.sum(ReviewLog.review_duration_ms)).where(
                ReviewLog.user_id == self.user_id,
                ReviewLog.reviewed_at >= today_start,
            )
        ).one() or 0

        # Cards by state (from UserCardProgress)
        state_counts = self.session.exec(
            select(UserCardProgress.state, func.count()).where(
                UserCardProgress.user_id == self.user_id,
            ).group_by(UserCardProgress.state)
        ).all()
        cards_by_state = {
            "new": new_cards, "learning": 0, "review": 0, "relearning": 0
        }
        state_names = {0: "new", 1: "learning", 2: "review", 3: "relearning"}
        for state_val, count in state_counts:
            name = state_names.get(state_val, "new")
            if name == "new":
                cards_by_state["new"] += count
            else:
                cards_by_state[name] = count

        # Retention rate (last 30 days)
        thirty_days_ago = now - timedelta(days=30)
        total_reviews_30d = self.session.exec(
            select(func.count()).where(
                ReviewLog.user_id == self.user_id,
                ReviewLog.reviewed_at >= thirty_days_ago,
            )
        ).one() or 0
        again_reviews_30d = self.session.exec(
            select(func.count()).where(
                ReviewLog.user_id == self.user_id,
                ReviewLog.reviewed_at >= thirty_days_ago,
                ReviewLog.rating == 1,
            )
        ).one() or 0
        retention_rate = (
            (total_reviews_30d - again_reviews_30d) / total_reviews_30d
            if total_reviews_30d > 0
            else 0.0
        )

        # Streak (consecutive days with reviews)
        streak = self._calculate_streak(tz=tz)

        # Category stats
        cat_stats = self._get_category_stats()

        # Daily reviews (last 30 days)
        daily_reviews = self._get_daily_reviews(30, tz=tz)

        return {
            "total_cards": total,
            "cards_due_today": due_today,
            "new_today": 0,
            "reviewed_today": reviewed_today,
            "streak_days": streak,
            "retention_rate": round(retention_rate, 4),
            "time_studied_today_ms": time_today,
            "cards_by_state": cards_by_state,
            "category_stats": cat_stats,
            "daily_reviews": daily_reviews,
        }

    def _calculate_streak(self, tz=None) -> int:
        """Calculate consecutive study days.

        If today has reviews, count today + consecutive past days.
        If today has no reviews yet, count from yesterday backwards
        (the user hasn't studied yet today but their streak isn't lost).

        When *tz* (a ZoneInfo instance) is provided, "today" is defined in
        the user's local timezone rather than UTC.  Day boundaries are
        converted to UTC before querying the database.
        """
        if tz:
            from zoneinfo import ZoneInfo
            now_local = datetime.now(tz)
        else:
            now_local = datetime.now(timezone.utc)

        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start_local = today_start_local + timedelta(days=1)

        # Convert local day boundaries to UTC for DB queries
        today_start_utc = today_start_local.astimezone(timezone.utc)
        tomorrow_start_utc = tomorrow_start_local.astimezone(timezone.utc)

        # Check if user has studied today
        today_count = self.session.exec(
            select(func.count()).where(
                ReviewLog.user_id == self.user_id,
                ReviewLog.reviewed_at >= today_start_utc,
                ReviewLog.reviewed_at < tomorrow_start_utc,
            )
        ).one()

        streak = 0
        if today_count > 0:
            streak = 1
            check_date = today_start_local - timedelta(days=1)
        else:
            # Start from yesterday — streak not broken yet
            check_date = today_start_local - timedelta(days=1)

        for _ in range(365):
            day_start_utc = check_date.astimezone(timezone.utc)
            day_end_utc = (check_date + timedelta(days=1)).astimezone(timezone.utc)
            count = self.session.exec(
                select(func.count()).where(
                    ReviewLog.user_id == self.user_id,
                    ReviewLog.reviewed_at >= day_start_utc,
                    ReviewLog.reviewed_at < day_end_utc,
                )
            ).one()
            if count > 0:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        return streak

    def _get_category_stats(self) -> list[dict]:
        """Get per-category card count and due count."""
        results = self.session.exec(
            select(
                Category.id,
                Category.name,
                Category.icon,
                func.count(Card.id),
            )
            .outerjoin(Card, Card.category_id == Category.id)
            .group_by(Category.id)
            .order_by(Category.sort_order)
        ).all()

        stats = []
        now = datetime.now(timezone.utc)
        for cat_id, name, icon, count in results:
            # Due count: progress-based due + new cards in this category
            due_progress = self.session.exec(
                select(func.count())
                .select_from(UserCardProgress)
                .join(Card, Card.id == UserCardProgress.card_id)
                .where(
                    UserCardProgress.user_id == self.user_id,
                    Card.category_id == cat_id,
                    UserCardProgress.is_suspended == False,
                    UserCardProgress.due <= now,
                )
            ).one()

            # Cards in category without progress = new/due
            cards_with_prog = self.session.exec(
                select(func.count())
                .select_from(UserCardProgress)
                .join(Card, Card.id == UserCardProgress.card_id)
                .where(
                    UserCardProgress.user_id == self.user_id,
                    Card.category_id == cat_id,
                )
            ).one()
            total_approved_cat = self.session.exec(
                select(func.count()).where(
                    Card.category_id == cat_id,
                )
            ).one()
            new_in_cat = max(0, total_approved_cat - cards_with_prog)
            due = due_progress + new_in_cat

            stats.append({
                "category_id": cat_id,
                "name": name,
                "icon": icon,
                "total_cards": count,
                "due_count": due,
            })
        return stats

    def _get_daily_reviews(self, days: int, tz=None) -> list[dict]:
        """Get review counts for the last N days.

        When *tz* is provided, day boundaries are computed in the user's
        local timezone.
        """
        if tz:
            now_local = datetime.now(tz)
        else:
            now_local = datetime.now(timezone.utc)

        daily = []
        for i in range(days):
            day_start_local = (now_local - timedelta(days=i)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            day_end_local = day_start_local + timedelta(days=1)
            day_start_utc = day_start_local.astimezone(timezone.utc)
            day_end_utc = day_end_local.astimezone(timezone.utc)
            count = self.session.exec(
                select(func.count()).where(
                    ReviewLog.user_id == self.user_id,
                    ReviewLog.reviewed_at >= day_start_utc,
                    ReviewLog.reviewed_at < day_end_utc,
                )
            ).one()
            daily.append({
                "date": day_start_local.strftime("%Y-%m-%d"),
                "count": count,
            })
        return list(reversed(daily))

    def _merge_card_progress(self, card: Card, progress: UserCardProgress | None) -> dict:
        """Merge a Card and its optional UserCardProgress into a flat dict
        compatible with CardResponse."""
        from app.models.tag import CardTag, Tag
        from app.models.category import Category

        now = datetime.now(timezone.utc)

        # Get category name
        cat_name = ""
        if card.category_id:
            cat = self.session.get(Category, card.category_id)
            if cat:
                cat_name = cat.name

        # Get tags
        tag_rows = self.session.exec(
            select(Tag.id, Tag.name, Tag.color)
            .join(CardTag, CardTag.tag_id == Tag.id)
            .where(CardTag.card_id == card.id)
        ).all()
        tags_list = [{"id": tid, "name": tname, "color": tcolor} for tid, tname, tcolor in tag_rows]

        d = {
            "id": card.id,
            "deck_id": card.deck_id,
            "category_id": card.category_id,
            "category_name": cat_name,
            "front": card.front,
            "back": card.back,
            "explanation": card.explanation,
            "distractors": card.distractors,
            "tags": card.tags,
            "tags_list": tags_list,
            "meta_info": card.meta_info,
            "source": card.source,
            "expires_at": card.expires_at,
            "is_ai_generated": card.is_ai_generated,
            "created_at": card.created_at,
            "updated_at": card.updated_at,
            # Progress fields
            "due": progress.due if progress else now,
            "stability": progress.stability if progress else 0.0,
            "difficulty": progress.difficulty if progress else 0.0,
            "state": progress.state if progress else CardState.NEW,
            "reps": progress.reps if progress else 0,
            "lapses": progress.lapses if progress else 0,
            "is_suspended": progress.is_suspended if progress else False,
        }
        return d
