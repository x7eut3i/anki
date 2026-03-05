#!/usr/bin/env python3
"""
Convert legacy content JSON files to the new schema format.

Legacy format:
  - card_type: "choice" | "basic" | "true_false"
  - back: letter like "A" or "B" (for choice), or text (for basic)
  - choices: JSON string of options like '["A. ...", "B. ...", ...]'
  - correct_answer: "A", "B", etc.

New format:
  - back: correct answer text (not a letter)
  - distractors: array of wrong answer texts
  - No card_type, choices, or correct_answer fields
  - meta_info: cleaned up (no distractors, no xingce/shenlun)
"""

import json
import re
import sys
from pathlib import Path


def convert_card(card: dict) -> dict:
    """Convert a single card from legacy to new format."""
    card_type = card.get("card_type", "")
    choices_raw = card.get("choices", "")
    correct_answer = card.get("correct_answer", "")
    back = card.get("back", "")

    # Parse choices
    choices = []
    if choices_raw:
        if isinstance(choices_raw, str):
            try:
                choices = json.loads(choices_raw)
            except (json.JSONDecodeError, TypeError):
                choices = []
        elif isinstance(choices_raw, list):
            choices = choices_raw

    if card_type == "choice" and choices:
        # Extract correct answer text and distractors
        answer_text = back
        distractors = []
        if correct_answer and len(correct_answer) == 1 and correct_answer.isalpha():
            idx = ord(correct_answer.upper()) - ord('A')
            if 0 <= idx < len(choices):
                raw_text = choices[idx]
                answer_text = re.sub(r'^[A-Z]\.\s*', '', raw_text)
                for i, ch in enumerate(choices):
                    if i != idx:
                        distractors.append(re.sub(r'^[A-Z]\.\s*', '', ch))
        elif back and back not in ("A", "B", "C", "D"):
            answer_text = back
            for ch in choices:
                text = re.sub(r'^[A-Z]\.\s*', '', ch)
                if text != answer_text:
                    distractors.append(text)
        card["back"] = answer_text
        card["distractors"] = distractors
    elif card_type == "true_false":
        if not back or back in ("对", "错", "正确", "错误"):
            card["back"] = correct_answer or back
        card["distractors"] = []
    else:
        card["distractors"] = []

    # Remove legacy fields
    card.pop("card_type", None)
    card.pop("choices", None)
    card.pop("correct_answer", None)

    # Clean up meta_info
    meta_raw = card.get("meta_info", "")
    if meta_raw and isinstance(meta_raw, str):
        try:
            meta = json.loads(meta_raw)
            # Remove distractors from meta_info (Issue 9)
            meta.pop("distractors", None)
            # Remove xingce/shenlun from exam_focus (Issue 10)
            if "exam_focus" in meta:
                meta["exam_focus"].pop("xingce_relevant", None)
                meta["exam_focus"].pop("shenlun_relevant", None)
            # Remove alternate_questions (not used)
            meta.pop("alternate_questions", None)
            card["meta_info"] = json.dumps(meta, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

    return card


def convert_file(filepath: Path) -> int:
    """Convert a single JSON file. Returns number of cards converted."""
    with open(filepath, "r", encoding="utf-8") as f:
        cards = json.load(f)

    if not isinstance(cards, list):
        print(f"  ⚠️  Skipping {filepath.name}: not a JSON array")
        return 0

    converted = 0
    for i, card in enumerate(cards):
        if "card_type" in card or "choices" in card or "correct_answer" in card:
            cards[i] = convert_card(card)
            converted += 1

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    return converted


def main():
    content_dir = Path(__file__).parent
    json_files = sorted(content_dir.glob("*.json"))

    if not json_files:
        print("No JSON files found in content directory")
        return

    total_converted = 0
    for filepath in json_files:
        count = convert_file(filepath)
        total_converted += count
        status = f"✅ {count} cards converted" if count > 0 else "⏭️  already converted"
        print(f"  {filepath.name}: {status}")

    print(f"\nTotal: {total_converted} cards converted across {len(json_files)} files")


if __name__ == "__main__":
    main()
