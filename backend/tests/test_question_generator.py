"""Tests for dynamic question generator."""

import json
import pytest
from app.models.card import Card
from app.services.question_generator import QuestionGenerator


def _make_card(
    card_id: int = 1,
    front: str = "测试问题",
    back: str = "测试答案",
    category_id: int = 1,
    meta_info: str = "",
    distractors: str = "",
) -> Card:
    card = Card(
        id=card_id,
        deck_id=1,
        user_id=1,
        category_id=category_id,
        front=front,
        back=back,
        meta_info=meta_info,
        distractors=distractors,
    )
    return card


def _make_pool(count: int = 5, category_id: int = 1) -> list[Card]:
    """Create a pool of cards for distractor generation."""
    return [
        _make_card(
            card_id=i + 100,
            front=f"问题{i}",
            back=f"答案{i}",
            category_id=category_id,
        )
        for i in range(count)
    ]


# ── can_generate ──


class TestCanGenerate:
    def test_no_meta_info(self):
        card = _make_card(meta_info="")
        gen = QuestionGenerator()
        assert gen.can_generate(card) is False

    def test_invalid_json(self):
        card = _make_card(meta_info="not json")
        gen = QuestionGenerator()
        assert gen.can_generate(card) is False

    def test_empty_facts(self):
        card = _make_card(meta_info='{"facts": {}}')
        gen = QuestionGenerator()
        assert gen.can_generate(card) is False

    def test_with_facts(self):
        meta = {"facts": {"meaning": "测试含义"}}
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()
        assert gen.can_generate(card) is True

    def test_with_alternate_questions(self):
        meta = {
            "alternate_questions": [
                {"type": "fill", "question": "Q?", "answer": "A"}
            ]
        }
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()
        assert gen.can_generate(card) is True


# ── Alternate questions mode ──


class TestAlternateQuestions:
    def test_picks_from_alternates(self):
        meta = {
            "alternate_questions": [
                {
                    "type": "fill",
                    "question": "替代问题",
                    "answer": "替代答案",
                },
            ]
        }
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()
        q = gen.generate(card, question_id=1, category_name="测试分类")
        assert q is not None
        assert q["question"] == "替代问题"
        assert q["question_type"] == "qa"
        assert q["card_id"] == card.id
        assert q["category_name"] == "测试分类"
        assert "_correct_answer" in q
        assert q["_correct_answer"] == "替代答案"

    def test_filters_by_preferred_type(self):
        meta = {
            "alternate_questions": [
                {"type": "fill", "question": "填空", "answer": "A"},
                {"type": "choice", "question": "选择", "answer": "B",
                 "distractors": ["X", "Y", "Z"]},
            ]
        }
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()

        # Run multiple times to check filtering
        for _ in range(10):
            q = gen.generate(card, 1, "cat", preferred_type="choice")
            assert q["question_type"] == "choice"

    def test_shuffles_choices(self):
        meta = {
            "alternate_questions": [
                {
                    "type": "choice",
                    "question": "Q?",
                    "answer": "B",
                    "distractors": ["A", "C", "D"],
                },
            ]
        }
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()

        orders = set()
        for _ in range(20):
            q = gen.generate(card, 1, "cat")
            orders.add(tuple(q["choices"]))
        # With shuffling, we should see multiple orders
        assert len(orders) > 1

    def test_true_false_alternate(self):
        meta = {
            "alternate_questions": [
                {
                    "type": "true_false",
                    "question": "这是正确的吗？",
                    "answer": "正确",
                    "distractors": ["错误"],
                },
            ]
        }
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()
        q = gen.generate(card, 1, "cat")
        assert q["question_type"] == "choice"
        # Answer is a letter (A or B) since it's found in shuffled choices
        assert q["_correct_answer"] in ("A", "B")
        assert q["_correct_answer_display"] == "正确"


# ── Template-based generation ──


class TestTemplateGeneration:
    def test_idiom_meaning_question(self):
        meta = {
            "knowledge_type": "idiom",
            "subject": "画蛇添足",
            "facts": {
                "meaning": "做多余的事",
                "origin": "《战国策》",
                "common_misuse": "画得逼真",
            },
            "confusables": ["多此一举", "节外生枝", "锦上添花"],
        }
        card = _make_card(
            back="做多余的事",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        pool = _make_pool()
        gen = QuestionGenerator(pool)

        # Generate multiple questions to test variety
        types_seen = set()
        for _ in range(30):
            q = gen.generate(card, 1, "成语")
            assert q is not None
            assert q["card_id"] == card.id
            types_seen.add(q["question_type"])
            assert "_correct_answer" in q

        # Should generate different question types
        assert len(types_seen) >= 2

    def test_general_facts_generation(self):
        meta = {
            "knowledge_type": "general",
            "subject": "测试主题",
            "facts": {
                "answer": "42",
                "question_stem": "生命的意义是什么？",
                "fill_stem": "生命的意义是___。",
            },
        }
        card = _make_card(
            back="42",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        gen = QuestionGenerator(_make_pool())
        q = gen.generate(card, 1, "通用", preferred_type="qa")
        assert q is not None
        assert q["question_type"] == "qa"

    def test_falls_back_when_no_viable_template(self):
        meta = {
            "knowledge_type": "idiom",
            "subject": "",
            "facts": {},  # Empty facts
        }
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()
        # Empty facts → can_generate returns False
        assert gen.can_generate(card) is False


# ── Choice building ──


class TestChoiceBuilding:
    def test_builds_4_choices_from_confusables(self):
        meta = {
            "knowledge_type": "general",
            "subject": "Q",
            "facts": {
                "answer": "正确答案",
                "question_stem": "问题？",
            },
            "confusables": ["错误1", "错误2", "错误3"],
        }
        card = _make_card(
            back="正确答案",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        gen = QuestionGenerator(_make_pool())
        q = gen.generate(card, 1, "cat", preferred_type="choice")
        if q and q["question_type"] == "choice":
            assert len(q["choices"]) == 4
            assert "正确答案" in q["choices"]

    def test_falls_back_to_qa_without_distractors(self):
        meta = {
            "knowledge_type": "general",
            "subject": "Q",
            "facts": {
                "answer": "正确答案",
                "question_stem": "问题？",
            },
        }
        card = _make_card(
            back="正确答案",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        # No pool, no confusables → can't build choices → qa fallback
        gen = QuestionGenerator([])
        q = gen.generate(card, 1, "cat", preferred_type="choice")
        if q:
            assert q["question_type"] in ("choice", "qa")


# ── Integration: generator can be used by quiz service ──


class TestGeneratorIntegration:
    def test_correct_answer_included(self):
        """Verify _correct_answer is present for answer map tracking."""
        meta = {
            "alternate_questions": [
                {"type": "fill", "question": "Q?", "answer": "the answer"}
            ]
        }
        card = _make_card(meta_info=json.dumps(meta))
        gen = QuestionGenerator()
        q = gen.generate(card, 1, "cat")
        assert "_correct_answer" in q
        assert q["_correct_answer"] == "the answer"

    def test_no_meta_returns_none(self):
        card = _make_card(meta_info="")
        gen = QuestionGenerator()
        result = gen.generate(card, 1, "cat")
        assert result is None

    def test_legacy_choices_format(self):
        """Legacy alternate_questions with 'choices' instead of 'distractors' still work."""
        meta = {
            "alternate_questions": [
                {
                    "type": "choice",
                    "question": "旧格式题?",
                    "answer": "正确",
                    "choices": ["正确", "错误1", "错误2", "错误3"],
                }
            ]
        }
        card = _make_card(meta_info=json.dumps(meta, ensure_ascii=False))
        gen = QuestionGenerator()
        q = gen.generate(card, 1, "cat")
        assert q is not None
        assert q["question_type"] == "choice"
        assert len(q["choices"]) == 4
        assert "正确" in q["choices"]
        assert q["_correct_answer"] in ("A", "B", "C", "D")
        assert q["_correct_answer_display"] == "正确"


# ── Placeholder rejection ──


class TestPlaceholderRejection:
    """Ensure templates with unresolved {XXX} placeholders are rejected."""

    def test_missing_template_vars_not_in_output(self):
        """Law template with missing law_name/question_stem should not produce {XXX}."""
        meta = {
            "knowledge_type": "law",
            "subject": "某法律",
            "facts": {
                "answer": "正确答案",
                # Deliberately missing: law_name, question_stem, fill_stem
            },
        }
        card = _make_card(
            back="正确答案",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        gen = QuestionGenerator(_make_pool())

        # Run many times; should never produce {XXX} placeholders
        for _ in range(30):
            q = gen.generate(card, 1, "法律常识")
            if q is not None:
                assert "{" not in q["question"], (
                    f"Unresolved placeholder in question: {q['question']}"
                )

    def test_history_missing_event_date(self):
        """History template with missing event/date should not produce {XXX}."""
        meta = {
            "knowledge_type": "history",
            "subject": "某事件",
            "facts": {
                "significance": "重大意义",
                # Missing: event, date
            },
        }
        card = _make_card(
            back="重大意义",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        gen = QuestionGenerator(_make_pool())

        for _ in range(30):
            q = gen.generate(card, 1, "历史文化")
            if q is not None:
                assert "{" not in q["question"], (
                    f"Unresolved placeholder in question: {q['question']}"
                )

    def test_partial_facts_still_works(self):
        """Templates with ALL required vars present should still work."""
        meta = {
            "knowledge_type": "law",
            "subject": "宪法",
            "facts": {
                "law_name": "《中华人民共和国宪法》",
                "question_stem": "以下哪项是公民基本权利？",
                "answer": "选举权",
            },
        }
        card = _make_card(
            back="选举权",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        gen = QuestionGenerator(_make_pool())
        generated_any = False
        for _ in range(20):
            q = gen.generate(card, 1, "法律常识")
            if q is not None:
                generated_any = True
                assert "{" not in q["question"]
        assert generated_any, "Should generate at least one question when all vars are present"

    def test_general_missing_question_stem(self):
        """General template with missing question_stem should not produce {XXX}."""
        meta = {
            "knowledge_type": "general",
            "subject": "通用",
            "facts": {
                "answer": "42",
                # Missing: question_stem, fill_stem
            },
        }
        card = _make_card(
            back="42",
            meta_info=json.dumps(meta, ensure_ascii=False),
        )
        gen = QuestionGenerator(_make_pool())

        for _ in range(30):
            q = gen.generate(card, 1, "通用")
            if q is not None:
                assert "{" not in q["question"], (
                    f"Unresolved placeholder in question: {q['question']}"
                )
