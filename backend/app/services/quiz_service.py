"""Quiz service: generates and scores quiz sessions."""

import json
import random
from datetime import datetime, timezone

from sqlmodel import Session, select, func, col

from app.models.card import Card
from app.models.category import Category
from app.models.study_session import StudySession
from app.services.question_generator import QuestionGenerator


class QuizService:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        self.user_id = user_id

    def generate_quiz(
        self,
        category_ids: list[int] | None = None,
        deck_ids: list[int] | None = None,
        card_count: int = 20,
        time_limit: int = 0,
        include_types: list[str] | None = None,
    ) -> dict:
        """Generate a quiz from the card pool."""
        if include_types is None:
            include_types = ["choice"]

        # Select cards, prioritizing those with low retrievability / high lapses
        query = select(Card)
        if category_ids:
            query = query.where(col(Card.category_id).in_(category_ids))
        if deck_ids:
            query = query.where(col(Card.deck_id).in_(deck_ids))

        # Get more cards than needed, then sample
        query = query.order_by(func.random()).limit(card_count * 3)
        cards = list(self.session.exec(query).all())

        if not cards:
            return {"session_id": 0, "questions": [], "total_questions": 0, "time_limit": 0}

        # Sample cards
        selected = random.sample(cards, min(card_count, len(cards)))

        # Pre-load tags for all selected cards
        from app.models.tag import CardTag, Tag
        sel_ids = [c.id for c in selected]
        card_tag_map: dict[int, list[dict]] = {}
        if sel_ids:
            tag_rows = self.session.exec(
                select(CardTag.card_id, Tag.id, Tag.name, Tag.color)
                .join(Tag, Tag.id == CardTag.tag_id)
                .where(col(CardTag.card_id).in_(sel_ids))
            ).all()
            for cid, tid, tname, tcolor in tag_rows:
                card_tag_map.setdefault(cid, []).append({"id": tid, "name": tname, "color": tcolor})

        # Generate questions
        questions = []
        all_cards = cards  # Use full pool for distractor generation
        generator = QuestionGenerator(all_cards)
        for i, card in enumerate(selected):
            q = self._card_to_question(card, i + 1, all_cards, include_types, generator,
                                        tags_list=card_tag_map.get(card.id, []))
            if q:
                questions.append(q)

        # Build answer map for dynamic questions (question_id → {answer, display})
        answer_map: dict[str, dict] = {}
        for q in questions:
            if "_correct_answer" in q:
                ans_letter = q.pop("_correct_answer")
                ans_display = q.pop("_correct_answer_display", "")
                answer_map[str(q["question_id"])] = {
                    "answer": ans_letter,
                    "display": ans_display,
                }

        # Create study session
        card_ids = [q["card_id"] for q in questions]
        session_obj = StudySession(
            user_id=self.user_id,
            mode="quiz",
            category_ids=",".join(str(c) for c in (category_ids or [])),
            total_cards=len(questions),
            quiz_time_limit=time_limit,
            remaining_card_ids=json.dumps(card_ids),
            quiz_answer_map=json.dumps(answer_map) if answer_map else "{}",
        )
        self.session.add(session_obj)
        self.session.commit()
        self.session.refresh(session_obj)

        return {
            "session_id": session_obj.id,
            "questions": questions,
            "total_questions": len(questions),
            "time_limit": time_limit,
        }

    def score_quiz(
        self,
        session_id: int,
        answers: list[dict],
    ) -> dict:
        """Score a submitted quiz."""
        study_session = self.session.get(StudySession, session_id)
        if not study_session or study_session.user_id != self.user_id:
            raise ValueError("Session not found")

        results = []
        correct_count = 0
        total_time = 0
        category_scores: dict[str, dict] = {}

        # Load dynamic answer map
        try:
            answer_map = json.loads(study_session.quiz_answer_map or "{}")
        except (json.JSONDecodeError, TypeError):
            answer_map = {}

        for ans in answers:
            card = self.session.get(Card, ans["card_id"])
            if not card:
                continue

            # Check dynamic answer map first, then fall back to card answer
            q_id = str(ans.get("question_id", 0))
            user_answer = ans.get("answer", "").strip()

            if q_id in answer_map:
                entry = answer_map[q_id]
                if isinstance(entry, dict):
                    correct = entry["answer"]
                    correct_display = entry.get("display") or correct
                else:
                    # Legacy: plain string
                    correct = entry
                    correct_display = correct
                    if len(correct) == 1 and correct.upper() in "ABCD":
                        correct_display = card.back
            else:
                correct = self._get_correct_answer(card)
                correct_display = correct

            # Compare: answer_map stores letters for choice Qs, text for Q&A
            is_correct = user_answer.lower() == correct.lower()

            if is_correct:
                correct_count += 1

            total_time += ans.get("time_spent_ms", 0)

            # Get category name
            cat_name = "未分类"
            if card.category_id:
                cat = self.session.get(Category, card.category_id)
                if cat:
                    cat_name = cat.name

            # Track per-category scores
            if cat_name not in category_scores:
                category_scores[cat_name] = {"correct": 0, "total": 0}
            category_scores[cat_name]["total"] += 1
            if is_correct:
                category_scores[cat_name]["correct"] += 1

            results.append({
                "question_id": ans.get("question_id", 0),
                "card_id": card.id,
                "correct": is_correct,
                "correct_answer": correct_display,
                "user_answer": user_answer,
                "explanation": card.explanation or card.back,
                "pinyin": self._extract_pinyin(card),
            })

        # Update session
        study_session.cards_reviewed = len(answers)
        study_session.cards_correct = correct_count
        study_session.cards_again = len(answers) - correct_count
        study_session.quiz_score = correct_count
        study_session.is_completed = True
        study_session.finished_at = datetime.now(timezone.utc)
        study_session.remaining_card_ids = "[]"
        self.session.add(study_session)
        self.session.commit()

        total = len(answers)
        return {
            "session_id": session_id,
            "score": correct_count,
            "total": total,
            "accuracy": round(correct_count / total, 4) if total > 0 else 0.0,
            "time_spent_ms": total_time,
            "results": results,
            "category_scores": category_scores,
        }

    def _card_to_question(
        self,
        card: Card,
        question_id: int,
        all_cards: list[Card],
        include_types: list[str],
        generator: QuestionGenerator | None = None,
        tags_list: list[dict] | None = None,
    ) -> dict | None:
        """Convert a card into a quiz question.

        Quiz mode (include_types=["choice"]): 100% multiple choice.
        Review/Mixed mode (include_types contains "qa"): 60% Q&A, 40% choice.
        """
        # Get category name
        cat_name = "未分类"
        if card.category_id:
            cat = self.session.get(Category, card.category_id)
            if cat:
                cat_name = cat.name

        # Determine preferred type based on mode
        # "choice" only = quiz/mock test mode → 100% MC
        # Contains "qa" = review/mixed mode → 60% Q&A, 40% MC
        preferred_type = "choice"
        if "qa" in include_types:
            preferred_type = "qa" if random.random() < 0.6 else "choice"

        # ── Dynamic generation from meta_info ──
        if generator and generator.can_generate(card):
            q = generator.generate(card, question_id, cat_name, preferred_type)
            if q:
                q["tags_list"] = tags_list or []
                return q

        # ── For Q&A preferred type, return Q&A question directly ──
        if preferred_type == "qa":
            return self._make_qa_question(card, question_id, cat_name, tags_list=tags_list)

        # ── Static choice: use card's own content ──

        # Parse distractors from the card
        card_distractors = self._parse_distractors(card)

        if card_distractors:
            return self._make_choice_question(card, question_id, cat_name, card_distractors, tags_list=tags_list)

        # Card has no distractors — try generating from pool
        pool_distractors = self._generate_distractors(card, all_cards, count=3)
        if pool_distractors:
            return self._make_choice_question(card, question_id, cat_name, pool_distractors, tags_list=tags_list)

        # Final fallback: still make a choice question with placeholder distractors
        return self._make_choice_question(card, question_id, cat_name, ["以上都不对", "无法确定", "题目信息不足"], tags_list=tags_list)

    def _parse_distractors(self, card: Card) -> list[str]:
        """Parse distractors JSON from card."""
        if not card.distractors:
            return []
        try:
            parsed = json.loads(card.distractors)
            return parsed if isinstance(parsed, list) and parsed else []
        except (json.JSONDecodeError, TypeError):
            return []

    def _make_choice_question(
        self, card: Card, question_id: int, cat_name: str, distractors: list[str],
        tags_list: list[dict] | None = None,
    ) -> dict:
        """Build a multiple-choice question."""
        choices = distractors[:3] + [card.back]
        random.shuffle(choices)
        # Determine the correct answer letter (A/B/C/D) after shuffle
        correct_idx = choices.index(card.back)
        correct_letter = chr(65 + correct_idx)  # A=65
        return {
            "question_id": question_id,
            "card_id": card.id,
            "question_type": "choice",
            "question": card.front,
            "choices": choices,
            "category_name": cat_name,
            "tags_list": tags_list or [],
            "time_limit": 0,
            "_correct_answer": correct_letter,
            "_correct_answer_display": card.back,
        }

    def _make_qa_question(
        self, card: Card, question_id: int, cat_name: str,
        tags_list: list[dict] | None = None,
    ) -> dict:
        """Build a Q&A (open-ended) question."""
        return {
            "question_id": question_id,
            "card_id": card.id,
            "question_type": "qa",
            "question": card.front,
            "choices": None,
            "category_name": cat_name,
            "tags_list": tags_list or [],
            "time_limit": 0,
        }

    def _generate_distractors(
        self, card: Card, all_cards: list[Card], count: int = 3
    ) -> list[str]:
        """Generate plausible wrong answers from other cards in the same category."""
        same_category = [
            c for c in all_cards
            if c.id != card.id
            and c.category_id == card.category_id
            and c.back != card.back
        ]
        if len(same_category) < count:
            # Fall back to any category
            same_category = [
                c for c in all_cards
                if c.id != card.id and c.back != card.back
            ]

        if len(same_category) < count:
            return []

        selected = random.sample(same_category, min(count, len(same_category)))
        return [c.back for c in selected]

    def _get_correct_answer(self, card: Card) -> str:
        """Get the correct answer for a card."""
        return card.back

    @staticmethod
    def _extract_pinyin(card: Card) -> str:
        """Extract pinyin from card meta_info, if present."""
        if not card.meta_info:
            return ""
        try:
            meta = json.loads(card.meta_info)
            return meta.get("pinyin", "")
        except (json.JSONDecodeError, TypeError):
            return ""
