"""Deduplication service: detects duplicate cards by normalized front text."""

import re
from sqlmodel import Session, select

from app.models.card import Card


def normalize_text(text: str) -> str:
    """Normalize text for comparison: strip, collapse whitespace, lowercase."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    # Remove common punctuation differences
    text = text.replace('，', ',').replace('。', '.').replace('；', ';')
    text = text.replace('：', ':').replace('？', '?').replace('！', '!')
    return text.lower()


class DedupService:
    def __init__(self, session: Session, user_id: int | None = None):
        self.session = session
        self.user_id = user_id  # kept for API compat but no longer used for filtering

    def check_duplicates(
        self,
        front_texts: list[str],
        category_id: int | None = None,
    ) -> list[dict]:
        """
        Check which front texts already exist as cards (shared).

        Returns a list of dicts: {front, is_duplicate, existing_card_id, existing_front}
        """
        # Build index of existing cards (shared — no user_id filter)
        query = select(Card)
        if category_id:
            query = query.where(Card.category_id == category_id)
        existing = self.session.exec(query).all()

        existing_index: dict[str, Card] = {}
        for card in existing:
            key = normalize_text(card.front)
            existing_index[key] = card

        results = []
        for front in front_texts:
            norm = normalize_text(front)
            existing_card = existing_index.get(norm)
            if existing_card:
                results.append({
                    "front": front,
                    "is_duplicate": True,
                    "existing_card_id": existing_card.id,
                    "existing_front": existing_card.front,
                })
            else:
                results.append({
                    "front": front,
                    "is_duplicate": False,
                    "existing_card_id": None,
                    "existing_front": None,
                })

        return results

    def find_duplicate(
        self,
        front_text: str,
        category_id: int | None = None,
        exclude_card_id: int | None = None,
    ) -> Card | None:
        """Find an existing card with the same front text (shared)."""
        norm = normalize_text(front_text)
        if not norm:
            return None

        query = select(Card)
        if category_id:
            query = query.where(Card.category_id == category_id)

        candidates = self.session.exec(query).all()
        for card in candidates:
            if exclude_card_id and card.id == exclude_card_id:
                continue
            if normalize_text(card.front) == norm:
                return card
        return None
