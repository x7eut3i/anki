"""Review service: handles card reviews, due card queries, and study stats."""

import hashlib
import json
import random
from datetime import datetime, timezone, timedelta

from sqlmodel import Session, select, func, col, text
from sqlalchemy import and_, or_, case

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
                stability=0.0,
                difficulty=0.0,
            )
            self.session.add(progress)
            self.session.commit()
            self.session.refresh(progress)
        return progress

    # ── Shared filter helper ────────────────────────────────────────

    def _resolve_card_filter(
        self,
        category_ids: list[int] | None,
        deck_id: int | None,
        deck_ids: list[int] | None,
        tag_ids: list[int] | None,
        exclude_ai_decks: bool = False,
    ):
        """Return a list of SQLAlchemy filter clauses and, if tag_ids
        filter yielded no cards, a flag indicating an empty result."""
        from app.models.deck import Deck

        filters = []

        if category_ids:
            # Cards with explicit category_id, OR cards without category_id
            # that belong to decks under the requested categories.
            cat_deck_ids = [d.id for d in self.session.exec(
                select(Deck).where(col(Deck.category_id).in_(category_ids))
            ).all()]
            conditions = [col(Card.category_id).in_(category_ids)]
            if cat_deck_ids:
                conditions.append(
                    and_(
                        Card.category_id == None,  # noqa: E711
                        col(Card.deck_id).in_(cat_deck_ids),
                    )
                )
            if deck_ids:
                conditions.append(col(Card.deck_id).in_(deck_ids))
            filters.append(or_(*conditions))
        elif deck_ids:
            filters.append(col(Card.deck_id).in_(deck_ids))
        elif deck_id is not None:
            filters.append(Card.deck_id == deck_id)

        if exclude_ai_decks:
            ai_deck_ids = [d.id for d in self.session.exec(
                select(Deck).where(col(Deck.name).startswith("AI-"))
            ).all()]
            if ai_deck_ids:
                filters.append(~col(Card.deck_id).in_(ai_deck_ids))

        if tag_ids:
            from app.models.tag import CardTag
            tagged_ids = list(self.session.exec(
                select(CardTag.card_id).where(col(CardTag.tag_id).in_(tag_ids))
            ).all())
            if tagged_ids:
                filters.append(col(Card.id).in_(tagged_ids))
            else:
                return filters, True  # empty result

        return filters, False

    def get_due_cards(
        self,
        category_ids: list[int] | None = None,
        deck_id: int | None = None,
        deck_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        exclude_ai_decks: bool = False,
        limit: int = 50,
    ) -> dict:
        """Get cards due for review using two split queries.

        Query 1: due cards (INNER JOIN) — cards with progress, due <= now
          Ordered: Relearning(3) > Learning(1) > Review(2), then by due ASC
        Query 2: new cards — cards without progress (appended after due cards)
          Ordered: date-seeded deterministic random

        Priority: Relearning > Learning > Review > New
        """
        now = datetime.now(timezone.utc)

        card_filters, empty = self._resolve_card_filter(
            category_ids, deck_id, deck_ids, tag_ids, exclude_ai_decks
        )
        if empty:
            return {"cards": [], "total_due": 0, "new_count": 0, "review_count": 0, "relearning_count": 0}

        card_valid = [(Card.expires_at == None) | (Card.expires_at > now)]

        # ── Query 1: due cards (have progress, due <= now) ──
        due_query = (
            select(Card, UserCardProgress)
            .join(
                UserCardProgress,
                (UserCardProgress.card_id == Card.id)
                & (UserCardProgress.user_id == self.user_id),
            )
            .where(
                *card_valid,
                *card_filters,
                UserCardProgress.is_suspended == False,
                UserCardProgress.due <= now,
            )
            .order_by(
                # Relearning(3)=0, Learning(1)=1, Review(2)=2
                text("""
                    CASE user_card_progress.state
                        WHEN 3 THEN 0
                        WHEN 1 THEN 1
                        WHEN 2 THEN 2
                        ELSE 3
                    END
                """),
                UserCardProgress.due.asc(),
            )
            .limit(limit)
        )
        due_rows = self.session.exec(due_query).all()

        # ── Query 2: new cards (no progress) ── only if slots remain
        remaining = limit - len(due_rows)
        new_rows: list = []
        if remaining > 0:
            # Subquery: card IDs this user already has progress for
            progress_subq = (
                select(UserCardProgress.card_id)
                .where(UserCardProgress.user_id == self.user_id)
            )
            # Date-seeded deterministic random order
            date_str = now.strftime("%Y-%m-%d")
            seed = int(hashlib.md5(f"{self.user_id}:{date_str}".encode()).hexdigest()[:8], 16)
            prime = 1000003

            new_query = (
                select(Card)
                .where(
                    *card_valid,
                    *card_filters,
                    ~col(Card.id).in_(progress_subq),
                )
                .order_by(text(f"(cards.id * {seed}) % {prime}"))
                .limit(remaining)
            )
            new_cards_list = list(self.session.exec(new_query).all())
            new_rows = [(card, None) for card in new_cards_list]

        # Merge results: due first, then new
        all_rows = list(due_rows) + new_rows

        # Batch-lookup article info
        article_cache = self._batch_lookup_articles([card for card, _ in all_rows])

        cards_with_progress = [
            self._merge_card_progress(card, progress, article_cache)
            for card, progress in all_rows
        ]

        # ── Counts (two simple queries) ──
        due_count = self.session.exec(
            select(func.count())
            .select_from(UserCardProgress)
            .join(Card, Card.id == UserCardProgress.card_id)
            .where(
                *card_valid,
                *card_filters,
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.is_suspended == False,
                UserCardProgress.due <= now,
            )
        ).one()

        total_with_progress = self.session.exec(
            select(func.count())
            .select_from(UserCardProgress)
            .join(Card, Card.id == UserCardProgress.card_id)
            .where(
                *card_valid,
                *card_filters,
                UserCardProgress.user_id == self.user_id,
            )
        ).one()

        total_approved = self.session.exec(
            select(func.count()).select_from(Card).where(*card_valid, *card_filters)
        ).one()

        new_count = max(0, total_approved - total_with_progress)

        # State breakdown for due cards
        state_counts = dict(self.session.exec(
            select(UserCardProgress.state, func.count())
            .join(Card, Card.id == UserCardProgress.card_id)
            .where(
                *card_valid,
                *card_filters,
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.is_suspended == False,
                UserCardProgress.due <= now,
            )
            .group_by(UserCardProgress.state)
        ).all())

        return {
            "cards": cards_with_progress,
            "total_due": due_count + new_count,
            "new_count": new_count,
            "review_count": state_counts.get(CardState.REVIEW, 0),
            "relearning_count": (
                state_counts.get(CardState.RELEARNING, 0)
                + state_counts.get(CardState.LEARNING, 0)
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
            "card_id": card_id,
            "due": progress.due if progress.due else now,
            "stability": progress.stability if progress.stability is not None else 0.0,
            "difficulty": progress.difficulty if progress.difficulty is not None else 0.0,
            "step": progress.step if progress.step is not None else 0,
            "reps": progress.reps if progress.reps is not None else 0,
            "lapses": progress.lapses if progress.lapses is not None else 0,
            "state": progress.state if progress.state is not None else 0,
            "last_review": progress.last_review if progress.last_review else None,
        }

        # Run FSRS — forward review_duration for Optimizer support
        updated, log_data = self.fsrs.review_card(
            card_data, rating, now,
            review_duration=duration_ms if duration_ms else None,
        )

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
            "card_id": card_id,
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

        # Shuffle cards for the session so the presentation order is random
        random.shuffle(card_ids)

        session_obj = StudySession(
            user_id=self.user_id,
            mode=mode,
            category_ids=",".join(str(c) for c in (category_ids or [])),
            deck_id=deck_id,
            total_cards=len(card_ids),
            remaining_card_ids=json.dumps(card_ids),
            all_card_ids=json.dumps(card_ids),
            quiz_time_limit=quiz_time_limit,
            question_mode=question_mode,
            custom_ratio=custom_ratio,
        )
        self.session.add(session_obj)
        self.session.commit()
        self.session.refresh(session_obj)
        return session_obj

    def get_active_session(self, exclude_modes: list[str] | None = None, only_mode: str | None = None) -> StudySession | None:
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
        if only_mode:
            query = query.where(StudySession.mode == only_mode)
        elif exclude_modes:
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

    def batch_update_session_progress(
        self, session_id: int, card_ids: list[int], is_correct_list: list[bool]
    ) -> StudySession:
        """Update session after reviewing multiple cards in one batch."""
        study_session = self.session.get(StudySession, session_id)
        if not study_session or study_session.user_id != self.user_id:
            raise ValueError("Session not found")

        remaining = json.loads(study_session.remaining_card_ids)
        newly_reviewed = 0
        correct = 0
        again = 0
        for card_id, is_ok in zip(card_ids, is_correct_list):
            if card_id in remaining:
                remaining.remove(card_id)
                newly_reviewed += 1
                if is_ok:
                    correct += 1
                else:
                    again += 1

        study_session.cards_reviewed += newly_reviewed
        study_session.cards_correct += correct
        study_session.cards_again += again
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
            tomorrow_end_local = today_start_local + timedelta(days=2)
            tomorrow_end_utc = tomorrow_end_local.astimezone(timezone.utc)
            today_end_local = today_start_local + timedelta(days=1)
            today_end_utc = today_end_local.astimezone(timezone.utc)
        else:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end_utc = today_start + timedelta(days=1)
            tomorrow_end_utc = today_start + timedelta(days=2)

        # Total cards (shared — all cards)
        total = self.session.exec(
            select(func.count()).select_from(Card)
        ).one()

        # Due review cards (have progress, due <= now, not suspended)
        due_review_count = self.session.exec(
            select(func.count()).where(
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.is_suspended == False,
                UserCardProgress.due <= now,
            )
        ).one()

        # New cards (no progress for this user, not expired)
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
        new_available_count = max(0, approved_cards - cards_with_progress)
        due_today = due_review_count + new_available_count

        # Batch: reviewed_today, time_today, new_cards_reviewed_today, retention (one query window)
        today_agg = self.session.exec(
            select(
                func.count(),
                func.coalesce(func.sum(ReviewLog.review_duration_ms), 0),
                func.sum(case((ReviewLog.state == 0, 1), else_=0)),  # new cards = state 0 before review
                func.sum(case((ReviewLog.rating == 1, 1), else_=0)),  # again count
            ).where(
                ReviewLog.user_id == self.user_id,
                ReviewLog.reviewed_at >= today_start,
            )
        ).one()
        reviewed_today = today_agg[0] or 0
        time_today = today_agg[1] or 0
        new_cards_reviewed_today = today_agg[2] or 0

        # Tomorrow due count: cards with progress whose due is between now and end of tomorrow
        tomorrow_due_count = self.session.exec(
            select(func.count()).where(
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.is_suspended == False,
                UserCardProgress.due > now,
                UserCardProgress.due <= tomorrow_end_utc,
            )
        ).one()

        # Cards by state (from UserCardProgress)
        state_counts = self.session.exec(
            select(UserCardProgress.state, func.count()).where(
                UserCardProgress.user_id == self.user_id,
            ).group_by(UserCardProgress.state)
        ).all()
        cards_by_state = {
            "new": new_available_count, "learning": 0, "review": 0, "relearning": 0
        }
        state_names = {0: "new", 1: "learning", 2: "review", 3: "relearning"}
        for state_val, count in state_counts:
            name = state_names.get(state_val, "new")
            if name == "new":
                cards_by_state["new"] += count
            else:
                cards_by_state[name] = count

        # Retention rate (last 30 days) — single query with conditional count
        thirty_days_ago = now - timedelta(days=30)
        ret_agg = self.session.exec(
            select(
                func.count(),
                func.sum(case((ReviewLog.rating == 1, 1), else_=0)),
            ).where(
                ReviewLog.user_id == self.user_id,
                ReviewLog.reviewed_at >= thirty_days_ago,
            )
        ).one()
        total_reviews_30d = ret_agg[0] or 0
        again_reviews_30d = ret_agg[1] or 0
        retention_rate = (
            (total_reviews_30d - again_reviews_30d) / total_reviews_30d
            if total_reviews_30d > 0
            else 0.0
        )

        # Streak (consecutive days with reviews) — single grouped query
        streak = self._calculate_streak(tz=tz)

        # Category stats — batch queries
        cat_stats = self._get_category_stats()

        # Daily reviews (last 30 days) — single grouped query
        daily_reviews = self._get_daily_reviews(30, tz=tz)

        return {
            "total_cards": total,
            "cards_due_today": due_today,
            "due_review_count": due_review_count,
            "new_available_count": new_available_count,
            "new_cards_reviewed_today": new_cards_reviewed_today,
            "tomorrow_due_count": tomorrow_due_count,
            "reviewed_today": reviewed_today,
            "streak_days": streak,
            "retention_rate": round(retention_rate, 4),
            "time_studied_today_ms": time_today,
            "cards_by_state": cards_by_state,
            "category_stats": cat_stats,
            "daily_reviews": daily_reviews,
        }

    def _calculate_streak(self, tz=None) -> int:
        """Calculate consecutive study days using a single grouped query.

        Fetches all distinct review dates in the last 365 days, then counts
        consecutive days in Python.
        """
        if tz:
            now_local = datetime.now(tz)
        else:
            now_local = datetime.now(timezone.utc)

        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        lookback_start = today_start_local - timedelta(days=365)
        lookback_start_utc = lookback_start.astimezone(timezone.utc)

        # Single query: get all distinct dates with reviews
        if tz:
            # Need to group by date in user's timezone
            # Use SQLite date arithmetic: reviewed_at + offset
            utc_offset_seconds = now_local.utcoffset().total_seconds()
            offset_str = f"+{int(utc_offset_seconds)} seconds" if utc_offset_seconds >= 0 else f"{int(utc_offset_seconds)} seconds"
            rows = self.session.exec(
                text(
                    "SELECT DISTINCT DATE(reviewed_at, :offset) as d "
                    "FROM review_logs "
                    "WHERE user_id = :uid AND reviewed_at >= :start "
                    "ORDER BY d DESC"
                ),
                params={"offset": offset_str, "uid": self.user_id, "start": lookback_start_utc},
            ).all()
        else:
            rows = self.session.exec(
                text(
                    "SELECT DISTINCT DATE(reviewed_at) as d "
                    "FROM review_logs "
                    "WHERE user_id = :uid AND reviewed_at >= :start "
                    "ORDER BY d DESC"
                ),
                params={"uid": self.user_id, "start": lookback_start_utc},
            ).all()

        if not rows:
            return 0

        # Convert to date set — rows are sqlalchemy.engine.row.Row, use [0]
        from datetime import date as date_type
        review_dates: set[date_type] = set()
        for row in rows:
            d_val = row[0]
            if isinstance(d_val, str):
                review_dates.add(date_type.fromisoformat(d_val))
            elif isinstance(d_val, date_type):
                review_dates.add(d_val)

        today = today_start_local.date()
        streak = 0
        if today in review_dates:
            streak = 1
            check = today - timedelta(days=1)
        else:
            # Today not yet studied — start from yesterday
            check = today - timedelta(days=1)

        while check in review_dates:
            streak += 1
            check -= timedelta(days=1)

        return streak

    def _get_category_stats(self) -> list[dict]:
        """Get per-category card count and due count using batch queries."""
        now = datetime.now(timezone.utc)

        # Query 1: category info with total card count
        cat_rows = self.session.exec(
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

        if not cat_rows:
            return []

        cat_ids = [r[0] for r in cat_rows]

        # Query 2: due progress count per category (batch)
        due_by_cat = dict(self.session.exec(
            select(Card.category_id, func.count())
            .select_from(UserCardProgress)
            .join(Card, Card.id == UserCardProgress.card_id)
            .where(
                UserCardProgress.user_id == self.user_id,
                UserCardProgress.is_suspended == False,
                UserCardProgress.due <= now,
                col(Card.category_id).in_(cat_ids),
            )
            .group_by(Card.category_id)
        ).all())

        # Query 3: cards with progress per category (batch)
        prog_by_cat = dict(self.session.exec(
            select(Card.category_id, func.count())
            .select_from(UserCardProgress)
            .join(Card, Card.id == UserCardProgress.card_id)
            .where(
                UserCardProgress.user_id == self.user_id,
                col(Card.category_id).in_(cat_ids),
            )
            .group_by(Card.category_id)
        ).all())

        stats = []
        for cat_id, name, icon, total_count in cat_rows:
            due_progress = due_by_cat.get(cat_id, 0)
            with_prog = prog_by_cat.get(cat_id, 0)
            new_in_cat = max(0, total_count - with_prog)
            stats.append({
                "category_id": cat_id,
                "name": name,
                "icon": icon,
                "total_cards": total_count,
                "due_count": due_progress + new_in_cat,
            })
        return stats

    def _get_daily_reviews(self, days: int, tz=None) -> list[dict]:
        """Get review counts for the last N days using a single grouped query."""
        if tz:
            now_local = datetime.now(tz)
        else:
            now_local = datetime.now(timezone.utc)

        start_local = (now_local - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start_utc = start_local.astimezone(timezone.utc)

        # Single query: group reviews by date
        if tz:
            utc_offset_seconds = now_local.utcoffset().total_seconds()
            offset_str = f"+{int(utc_offset_seconds)} seconds" if utc_offset_seconds >= 0 else f"{int(utc_offset_seconds)} seconds"
            rows = self.session.exec(
                text(
                    "SELECT DATE(reviewed_at, :offset) as d, COUNT(*) as c "
                    "FROM review_logs "
                    "WHERE user_id = :uid AND reviewed_at >= :start "
                    "GROUP BY d ORDER BY d"
                ),
                params={"offset": offset_str, "uid": self.user_id, "start": start_utc},
            ).all()
        else:
            rows = self.session.exec(
                text(
                    "SELECT DATE(reviewed_at) as d, COUNT(*) as c "
                    "FROM review_logs "
                    "WHERE user_id = :uid AND reviewed_at >= :start "
                    "GROUP BY d ORDER BY d"
                ),
                params={"uid": self.user_id, "start": start_utc},
            ).all()

        # Build date→count map
        count_map = {}
        for row in rows:
            count_map[row[0]] = row[1]

        # Fill in all dates (including zeros)
        daily = []
        for i in range(days):
            day = (now_local - timedelta(days=days - 1 - i)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            date_str = day.strftime("%Y-%m-%d")
            daily.append({"date": date_str, "count": count_map.get(date_str, 0)})

        return daily

    def get_cards_by_ids(self, card_ids: list[int]) -> list[dict]:
        """Fetch cards by IDs with their progress info (no SRS filtering).
        Used for session resume with history — returns reviewed + unreviewed cards.
        """
        if not card_ids:
            return []

        rows = self.session.exec(
            select(Card, UserCardProgress)
            .outerjoin(
                UserCardProgress,
                (UserCardProgress.card_id == Card.id)
                & (UserCardProgress.user_id == self.user_id),
            )
            .where(col(Card.id).in_(card_ids))
        ).all()

        article_cache = self._batch_lookup_articles([card for card, _ in rows])
        cards = [self._merge_card_progress(card, progress, article_cache) for card, progress in rows]

        # Maintain original order from card_ids
        id_order = {cid: i for i, cid in enumerate(card_ids)}
        cards.sort(key=lambda c: id_order.get(c["id"], 999999))
        return cards

    def _batch_lookup_articles(self, cards: list[Card]) -> dict[str, dict]:
        """Batch-lookup ArticleAnalysis records by card source URLs.
        Returns a dict keyed by source URL with article info."""
        from app.models.article_analysis import ArticleAnalysis

        source_urls = list({c.source for c in cards if c.source})
        if not source_urls:
            return {}

        items = self.session.exec(
            select(ArticleAnalysis.id, ArticleAnalysis.title,
                   ArticleAnalysis.quality_score, ArticleAnalysis.source_name,
                   ArticleAnalysis.source_url)
            .where(col(ArticleAnalysis.source_url).in_(source_urls))
        ).all()
        result: dict[str, dict] = {}
        for aid, atitle, aqscore, asname, aurl in items:
            if aurl and aurl not in result:
                result[aurl] = {
                    "id": aid,
                    "title": atitle,
                    "quality_score": aqscore,
                    "source_name": asname or "",
                }
        return result

    def _merge_card_progress(self, card: Card, progress: UserCardProgress | None, article_cache: dict[str, dict] | None = None) -> dict:
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
            "stability": (progress.stability if progress.stability is not None else 0.0) if progress else 0.0,
            "difficulty": (progress.difficulty if progress.difficulty is not None else 0.0) if progress else 0.0,
            "state": progress.state if progress else CardState.NEW,
            "reps": progress.reps if progress else 0,
            "lapses": progress.lapses if progress else 0,
            "is_suspended": progress.is_suspended if progress else False,
        }
        # Article info from cache
        if article_cache and card.source and card.source in article_cache:
            art = article_cache[card.source]
            d["article_id"] = art["id"]
            d["article_title"] = art["title"]
            d["article_quality_score"] = art["quality_score"]
            d["article_source_name"] = art["source_name"]

        # Scheduling preview: compute next-due for each rating
        try:
            card_data = {
                "card_id": card.id,
                "due": d["due"],
                "stability": d["stability"],
                "difficulty": d["difficulty"],
                "step": progress.step if progress else 0,
                "reps": d["reps"],
                "lapses": d["lapses"],
                "state": d["state"],
                "last_review": progress.last_review if progress else None,
            }
            p = self.fsrs.preview_ratings(card_data)
            d["scheduling_preview"] = {
                "1": f"{p['again_days']}天" if p.get('again_days', 0) > 0 else "<1天",
                "2": f"{p['hard_days']}天" if p.get('hard_days', 0) > 0 else "<1天",
                "3": f"{p['good_days']}天" if p.get('good_days', 0) > 0 else "<1天",
                "4": f"{p['easy_days']}天" if p.get('easy_days', 0) > 0 else "<1天",
            }
        except Exception:
            pass

        return d

    # ── Reset progress ────────────────────────────────────────────────

    def reset_all(self) -> dict:
        """Reset ALL study progress. All cards return to NEW state."""
        # Count before deleting
        progress_list = self.session.exec(
            select(UserCardProgress).where(UserCardProgress.user_id == self.user_id)
        ).all()
        review_logs = self.session.exec(
            select(ReviewLog).where(ReviewLog.user_id == self.user_id)
        ).all()

        progress_deleted = len(progress_list)
        reviews_deleted = len(review_logs)

        for p in progress_list:
            self.session.delete(p)
        for r in review_logs:
            self.session.delete(r)

        # Also clean up all study sessions
        sessions = self.session.exec(
            select(StudySession).where(StudySession.user_id == self.user_id)
        ).all()
        for s in sessions:
            self.session.delete(s)

        self.session.commit()
        return {"progress_deleted": progress_deleted, "reviews_deleted": reviews_deleted}
