"""Dynamic question generator: creates varied quiz questions from card meta_info.

Meta-info structure (new simplified format):
{
  "knowledge_type": "idiom|law|history|geography|science|politics|economics|general",
  "subject": "核心主题",
  "distractors": ["干扰项1", "干扰项2", "干扰项3"],
  "knowledge": {
    "synonyms": [...], "antonyms": [...], "related": [...],
    "key_points": [...], "golden_quotes": [...], "formal_terms": [...],
    "essay_material": "...", "memory_tips": "..."
  },
  "alternate_questions": [
    {"type": "choice|qa", "question": "...", "answer": "...", "distractors": [...]}
  ],
  "facts": {"key1": "value1", ...}
}
"""

import json
import random
import re
from typing import Any

from app.models.card import Card

# Pattern that matches unresolved template placeholders like {law_name}
_UNRESOLVED_PLACEHOLDER = re.compile(r'\{[a-zA-Z_]\w*\}')


# ── Template registry ────────────────────────────────────────────────

_TEMPLATES: dict[str, list[dict]] = {
    # ── 成语 (idiom) ──
    "idiom": [
        {
            "type": "choice",
            "question": "「{subject}」的正确含义是？",
            "answer_key": "meaning",
            "distractor_keys": ["common_misuse"],
        },
        {
            "type": "qa",
            "question": "「{subject}」出自哪里？",
            "answer_key": "origin",
        },
        {
            "type": "qa",
            "question": "请解释成语「{subject}」的含义。",
            "answer_key": "meaning",
        },
        {
            "type": "choice",
            "question": "以下哪个成语与「{subject}」含义最接近？",
            "answer_key": "similar",
            "use_first": True,
        },
        {
            "type": "qa",
            "question": "成语「{subject}」中「{key_char}」字的意思是什么？",
            "answer_key": "key_char_meaning",
            "requires": ["key_char", "key_char_meaning"],
        },
    ],

    # ── 法律 (law) ──
    "law": [
        {
            "type": "choice",
            "question": "根据{law_name}，{question_stem}",
            "answer_key": "answer",
        },
        {
            "type": "qa",
            "question": "{law_name}规定，{fill_stem}",
            "answer_key": "answer",
        },
    ],

    # ── 历史 (history) ──
    "history": [
        {
            "type": "choice",
            "question": "「{event}」发生在哪一年？",
            "answer_key": "date",
        },
        {
            "type": "qa",
            "question": "{event}的历史意义是什么？",
            "answer_key": "significance",
        },
        {
            "type": "choice",
            "question": "以下哪个事件发生在{date}？",
            "answer_key": "event",
        },
    ],

    # ── 地理 (geography) ──
    "geography": [
        {
            "type": "choice",
            "question": "{question_stem}",
            "answer_key": "answer",
        },
        {
            "type": "qa",
            "question": "{fill_stem}",
            "answer_key": "answer",
        },
    ],

    # ── 文学 (literature) ──
    "literature": [
        {
            "type": "choice",
            "question": "「{work}」的作者是？",
            "answer_key": "author",
        },
        {
            "type": "qa",
            "question": "「{quote}」出自{author}的哪部作品？",
            "answer_key": "work",
            "requires": ["quote"],
        },
        {
            "type": "choice",
            "question": "以下哪部作品属于{dynasty}时期？",
            "answer_key": "work",
            "requires": ["dynasty"],
        },
    ],

    # ── 通用 (general) ──
    "general": [
        {
            "type": "choice",
            "question": "{question_stem}",
            "answer_key": "answer",
        },
        {
            "type": "qa",
            "question": "{fill_stem}",
            "answer_key": "answer",
        },
    ],
}


class QuestionGenerator:
    """Generates varied quiz questions from card meta_info."""

    def __init__(self, all_cards: list[Card] | None = None):
        self.all_cards = all_cards or []

    def can_generate(self, card: Card) -> bool:
        """Check if this card has meta_info for dynamic generation."""
        if not card.meta_info:
            return False
        try:
            meta = json.loads(card.meta_info)
            return bool(meta.get("facts") or meta.get("alternate_questions"))
        except (json.JSONDecodeError, TypeError):
            return False

    def generate(
        self,
        card: Card,
        question_id: int,
        category_name: str,
        preferred_type: str | None = None,
    ) -> dict | None:
        """Generate a random question variant from card meta_info.

        Returns a quiz question dict or None if generation fails.
        """
        try:
            meta = json.loads(card.meta_info)
        except (json.JSONDecodeError, TypeError):
            return None

        # Method 1: Pre-defined alternate questions (highest priority)
        alt_questions = meta.get("alternate_questions")
        if alt_questions:
            return self._from_alternate(
                card, meta, alt_questions, question_id, category_name, preferred_type
            )

        # Method 2: Template-based generation from facts
        facts = meta.get("facts", {})
        if facts:
            return self._from_template(
                card, meta, facts, question_id, category_name, preferred_type
            )

        return None

    # ── Private helpers ──────────────────────────────────────────────

    def _from_alternate(
        self,
        card: Card,
        meta: dict,
        alt_questions: list[dict],
        question_id: int,
        category_name: str,
        preferred_type: str | None,
    ) -> dict | None:
        """Pick from pre-defined alternate question variants."""
        candidates = alt_questions
        if preferred_type:
            # Map old types to new for backward compat
            type_map = {"fill": "qa", "true_false": "choice", "basic": "qa"}
            target = type_map.get(preferred_type, preferred_type)
            typed = [q for q in candidates if type_map.get(q.get("type"), q.get("type")) == target]
            if typed:
                candidates = typed

        picked = random.choice(candidates)
        q_type = picked.get("type", "qa")
        # Normalize old types
        if q_type in ("fill", "basic"):
            q_type = "qa"
        elif q_type == "true_false":
            q_type = "choice"

        # Determine correct answer for scoring
        answer = picked.get("answer", picked.get("correct_answer", card.back))

        # Build choices from distractors + answer (new format)
        # Also supports legacy format with "choices" field
        distractors = picked.get("distractors") or []
        if not distractors:
            legacy_choices = picked.get("choices")
            if legacy_choices and isinstance(legacy_choices, list):
                # Legacy: extract distractors by removing answer
                distractors = [c for c in legacy_choices if c != str(answer)]

        choices = None
        if q_type == "choice" and distractors:
            choices = list(distractors[:3]) + [str(answer)]
            random.shuffle(choices)

        # For choice questions, convert text answer to letter (A/B/C/D)
        correct_for_map = str(answer)
        if q_type == "choice" and choices:
            try:
                correct_idx = choices.index(str(answer))
                correct_for_map = chr(65 + correct_idx)
            except ValueError:
                correct_for_map = str(answer)

        return {
            "question_id": question_id,
            "card_id": card.id,
            "question_type": q_type,
            "question": picked["question"],
            "choices": choices,
            "category_name": category_name,
            "time_limit": 0,
            "_correct_answer": correct_for_map,
            "_correct_answer_display": str(answer),
        }

    def _from_template(
        self,
        card: Card,
        meta: dict,
        facts: dict,
        question_id: int,
        category_name: str,
        preferred_type: str | None,
    ) -> dict | None:
        """Generate question from templates + facts."""
        knowledge_type = meta.get("knowledge_type", "general")
        templates = _TEMPLATES.get(knowledge_type, _TEMPLATES["general"])

        # Filter by preferred type
        if preferred_type:
            typed = [t for t in templates if t["type"] == preferred_type]
            if typed:
                templates = typed

        # Collect context dict for formatting
        context = {"subject": meta.get("subject", "")}
        context.update(facts)

        # Filter templates that have required fields
        viable = []
        for tmpl in templates:
            required = tmpl.get("requires", [])
            if all(context.get(r) for r in required):
                # Check the question format string can be satisfied
                try:
                    formatted = tmpl["question"].format_map(_SafeDict(context))
                    # Reject if unresolved placeholders remain (e.g. {law_name})
                    if _UNRESOLVED_PLACEHOLDER.search(formatted):
                        continue
                    viable.append(tmpl)
                except (KeyError, IndexError):
                    continue
            elif not required:
                try:
                    formatted = tmpl["question"].format_map(_SafeDict(context))
                    if _UNRESOLVED_PLACEHOLDER.search(formatted):
                        continue
                    viable.append(tmpl)
                except (KeyError, IndexError):
                    continue

        if not viable:
            return None

        tmpl = random.choice(viable)
        return self._apply_template(
            card, meta, facts, context, tmpl, question_id, category_name
        )

    def _apply_template(
        self,
        card: Card,
        meta: dict,
        facts: dict,
        context: dict,
        tmpl: dict,
        question_id: int,
        category_name: str,
    ) -> dict | None:
        """Apply a template to generate a concrete question."""
        q_type = tmpl["type"]
        safe_ctx = _SafeDict(context)

        try:
            question_text = tmpl["question"].format_map(safe_ctx)
        except (KeyError, IndexError):
            return None

        # Reject if unresolved placeholders remain
        if _UNRESOLVED_PLACEHOLDER.search(question_text):
            return None

        # Determine the answer
        answer_key = tmpl.get("answer_key", "answer")
        answer = tmpl.get("answer")  # Static answer (for true_false)
        if not answer:
            raw = facts.get(answer_key, card.back)
            if isinstance(raw, list):
                answer = raw[0] if tmpl.get("use_first") and raw else "；".join(raw)
            else:
                answer = str(raw)

        choices = None

        if q_type == "choice":
            choices = self._build_choices(card, meta, facts, answer, answer_key)
            if not choices:
                # Fallback to qa
                q_type = "qa"

        # For choice questions, convert text answer to letter (A/B/C/D)
        correct_for_map = str(answer)
        if q_type == "choice" and choices:
            try:
                correct_idx = choices.index(str(answer))
                correct_for_map = chr(65 + correct_idx)
            except ValueError:
                correct_for_map = str(answer)

        return {
            "question_id": question_id,
            "card_id": card.id,
            "question_type": q_type,
            "question": question_text,
            "choices": choices,
            "category_name": category_name,
            "time_limit": 0,
            "_correct_answer": correct_for_map,
            "_correct_answer_display": str(answer),
        }

    def _build_choices(
        self,
        card: Card,
        meta: dict,
        facts: dict,
        correct_answer: str,
        answer_key: str,
    ) -> list[str] | None:
        """Build 4 choices including the correct answer."""
        distractors: list[str] = []

        # Source 1: distractors from meta_info (new format)
        meta_distractors = meta.get("distractors", [])
        if meta_distractors and isinstance(meta_distractors, list):
            distractors.extend(meta_distractors)

        # Source 2: confusables from meta_info (legacy compat)
        confusables = meta.get("confusables", [])
        if confusables:
            distractors.extend(confusables)

        # Source 3: distractors from card field itself
        if not distractors and card.distractors:
            try:
                parsed = json.loads(card.distractors)
                if isinstance(parsed, list):
                    distractors.extend(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

        # Source 4: other cards' answers in same category
        if len(distractors) < 3:
            for c in self.all_cards:
                if c.id != card.id and c.category_id == card.category_id:
                    if c.back and c.back != correct_answer and c.back not in distractors:
                        distractors.append(c.back)
                        if len(distractors) >= 6:
                            break

        # Deduplicate and remove the correct answer
        seen = {correct_answer}
        unique_distractors = []
        for d in distractors:
            d_clean = d.strip()
            if d_clean and d_clean not in seen:
                seen.add(d_clean)
                unique_distractors.append(d_clean)

        if len(unique_distractors) < 3:
            return None

        # Pick 3 distractors + 1 correct → shuffle
        picked = random.sample(unique_distractors, min(3, len(unique_distractors)))
        choices = picked + [correct_answer]
        random.shuffle(choices)
        return choices


class _SafeDict(dict):
    """Dict subclass that returns the key wrapped in braces for missing keys."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
