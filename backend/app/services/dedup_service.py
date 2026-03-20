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
        # Lazily-built indexes
        self._by_cat: dict[tuple[int | None, str], Card] | None = None  # (category_id, norm) → Card
        self._by_front: dict[str, Card] | None = None  # norm → Card (any category)

    def _ensure_index(self):
        """Build (or return cached) normalized-front index."""
        if self._by_cat is not None:
            return
        query = select(Card)
        existing = self.session.exec(query).all()
        by_cat: dict[tuple[int | None, str], Card] = {}
        by_front: dict[str, Card] = {}
        for card in existing:
            norm = normalize_text(card.front)
            by_cat[(card.category_id, norm)] = card
            by_front[norm] = card
        self._by_cat = by_cat
        self._by_front = by_front

    def _lookup(self, norm: str, category_id: int | None) -> Card | None:
        """Look up by (category_id, norm) if category given, else by norm only."""
        self._ensure_index()
        if category_id is not None:
            return self._by_cat.get((category_id, norm))
        return self._by_front.get(norm)

    def check_duplicates(
        self,
        front_texts: list[str],
        category_id: int | None = None,
    ) -> list[dict]:
        """
        Check which front texts already exist as cards (shared).

        Returns a list of dicts: {front, is_duplicate, existing_card_id, existing_front}
        """
        idx = self._ensure_index()

        results = []
        for front in front_texts:
            norm = normalize_text(front)
            existing_card = self._lookup(norm, category_id)
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

        card = self._lookup(norm, category_id)
        if card and exclude_card_id and card.id == exclude_card_id:
            return None
        return card
