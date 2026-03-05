"""Enrich existing content files with meta_info for dynamic question generation.

This script reads JSON content files and generates meta_info for each card
based on its card_type, category, and content. The meta_info enables the
QuestionGenerator to produce varied questions from the same knowledge point.

Usage:
    python enrich_content.py                    # Dry run
    python enrich_content.py --apply            # Apply changes
    python enrich_content.py --file 01_成语.json  # Single file
"""

import json
import re
import sys
from pathlib import Path

CONTENT_DIR = Path(__file__).parent / "content"

# ── Category → knowledge_type mapping ──
CATEGORY_KNOWLEDGE_TYPE = {
    "成语": "idiom",
    "词语辨析": "general",
    "文学常识": "literature",
    "古诗文": "literature",
    "法律常识": "law",
    "经济常识": "general",
    "政治理论": "general",
    "历史知识": "history",
    "地理常识": "geography",
    "科技常识": "general",
    "逻辑推理": "general",
    "数量关系": "general",
    "资料分析": "general",
    "言语理解": "general",
    "时政热点": "general",
    "公文写作": "general",
    "申论技巧": "general",
    "面试技巧": "general",
    "行测技巧": "general",
    "常识判断": "general",
}


def extract_category_from_filename(filename: str) -> str:
    """Extract category name from filename like '01_成语.json' → '成语'."""
    name = Path(filename).stem
    parts = name.split("_", 1)
    return parts[1] if len(parts) > 1 else name


def enrich_idiom_card(card: dict) -> dict:
    """Generate meta_info for idiom cards."""
    front = card.get("front", "")
    back = card.get("back", "")
    explanation = card.get("explanation", "")

    # Extract idiom subject from front or explanation
    idiom_match = re.search(r"[「『](.+?)[」』]", front)
    subject = idiom_match.group(1) if idiom_match else ""

    if not subject:
        # Try to find a 4-char idiom in the front
        four_char = re.findall(r"[\u4e00-\u9fff]{4}", front)
        if four_char:
            subject = four_char[0]

    facts: dict = {}
    if subject:
        facts["subject_idiom"] = subject

    # Extract meaning from back or explanation
    if card.get("card_type") == "basic":
        facts["meaning"] = back
    elif card.get("card_type") == "choice":
        facts["correct_option"] = back

    # Try to extract origin from explanation
    origin_match = re.search(r"出自[《「](.+?)[》」]", explanation)
    if origin_match:
        facts["origin"] = origin_match.group(1)

    # Try to extract common misuse
    misuse_match = re.search(r"误[用解][为]?[「『]?(.+?)[」』。，]", explanation)
    if misuse_match:
        facts["common_misuse"] = misuse_match.group(1)

    # Build alternate questions
    alt_questions = []

    if subject and card.get("card_type") == "basic":
        # Reverse question: from meaning to idiom
        alt_questions.append({
            "type": "fill",
            "question": f"请写出与以下含义对应的成语：{back[:50]}",
            "answer": subject,
        })

    if subject and explanation:
        # True/false from explanation
        alt_questions.append({
            "type": "true_false",
            "question": f"以下关于「{subject}」的解释是否正确：{explanation[:80]}",
            "answer": "对",
            "choices": ["正确", "错误"],
        })

    meta = {
        "knowledge_type": "idiom",
        "subject": subject,
        "facts": facts,
    }
    if alt_questions:
        meta["alternate_questions"] = alt_questions

    return meta


def enrich_law_card(card: dict) -> dict:
    """Generate meta_info for law cards."""
    front = card.get("front", "")
    back = card.get("back", "")
    explanation = card.get("explanation", "")

    facts: dict = {}

    # Try to extract law name
    law_match = re.search(r"[《「](.+?)[》」]", front)
    if law_match:
        facts["law_name"] = law_match.group(1)

    # Extract key numbers
    numbers = re.findall(r"(\d+)\s*(?:周岁|日|年|条|款|项)", explanation)
    if numbers:
        facts["key_numbers"] = numbers

    alt_questions = []

    if card.get("card_type") == "choice" and card.get("choices"):
        # Create a fill version
        alt_questions.append({
            "type": "fill",
            "question": re.sub(r"[：:]\s*$", "___。", front),
            "answer": back,
        })

    meta = {
        "knowledge_type": "law",
        "subject": front[:30],
        "facts": facts,
    }
    if alt_questions:
        meta["alternate_questions"] = alt_questions

    return meta


def enrich_literature_card(card: dict) -> dict:
    """Generate meta_info for literature cards."""
    front = card.get("front", "")
    back = card.get("back", "")
    explanation = card.get("explanation", "")

    facts: dict = {}

    # Extract work title
    work_match = re.search(r"[《](.+?)[》]", front + " " + explanation)
    if work_match:
        facts["work"] = work_match.group(1)

    # Extract author
    author_patterns = [
        r"(.{2,4})(?:的|所著|所作|著|作)",
        r"作者(?:是|为)(.{2,4})",
    ]
    for pattern in author_patterns:
        m = re.search(pattern, front + " " + explanation)
        if m:
            facts["author"] = m.group(1)
            break

    meta = {
        "knowledge_type": "literature",
        "subject": front[:30],
        "facts": facts,
    }
    return meta


def enrich_history_card(card: dict) -> dict:
    """Generate meta_info for history cards."""
    front = card.get("front", "")
    back = card.get("back", "")
    explanation = card.get("explanation", "")

    facts: dict = {}

    # Extract dates
    date_match = re.search(r"(\d{3,4})年", front + " " + explanation)
    if date_match:
        facts["date"] = date_match.group(0)

    meta = {
        "knowledge_type": "history",
        "subject": front[:30],
        "facts": facts,
    }
    return meta


def enrich_general_card(card: dict) -> dict:
    """Generic meta_info for any card type."""
    front = card.get("front", "")
    back = card.get("back", "")
    explanation = card.get("explanation", "")

    alt_questions = []

    card_type = card.get("card_type", "basic")

    if card_type == "basic" and len(back) < 100:
        # Create a reverse question
        alt_questions.append({
            "type": "fill",
            "question": f"以下描述对应的概念是什么？{back[:80]}",
            "answer": front.rstrip("？?。."),
        })

    if card_type == "choice" and card.get("choices"):
        # Add fill variant
        alt_questions.append({
            "type": "fill",
            "question": front.rstrip("：:") + "___。",
            "answer": back,
        })

    meta = {
        "knowledge_type": "general",
        "subject": front[:30],
        "facts": {"answer": back},
    }
    if explanation:
        meta["facts"]["explanation_summary"] = explanation[:100]
    if alt_questions:
        meta["alternate_questions"] = alt_questions

    return meta


# ── Enrichment dispatcher ──

ENRICHERS = {
    "idiom": enrich_idiom_card,
    "law": enrich_law_card,
    "literature": enrich_literature_card,
    "history": enrich_history_card,
    "geography": enrich_general_card,
    "general": enrich_general_card,
}


def enrich_file(filepath: Path, apply: bool = False) -> int:
    """Enrich a single content file. Returns count of enriched cards."""
    with open(filepath, "r", encoding="utf-8") as f:
        cards = json.load(f)

    category = extract_category_from_filename(filepath.name)
    knowledge_type = CATEGORY_KNOWLEDGE_TYPE.get(category, "general")
    enricher = ENRICHERS.get(knowledge_type, enrich_general_card)

    enriched = 0
    for card in cards:
        if card.get("meta_info"):
            continue  # Already enriched

        meta = enricher(card)
        if meta and meta.get("facts"):
            card["meta_info"] = json.dumps(meta, ensure_ascii=False)
            enriched += 1

    if apply and enriched > 0:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cards, f, ensure_ascii=False, indent=2)

    return enriched


def main():
    apply = "--apply" in sys.argv
    target_file = None

    for arg in sys.argv[1:]:
        if arg.startswith("--file="):
            target_file = arg.split("=", 1)[1]
        elif arg == "--apply":
            continue

    if target_file:
        files = [CONTENT_DIR / target_file]
    else:
        files = sorted(CONTENT_DIR.glob("*.json"))

    total_enriched = 0
    for fp in files:
        if not fp.exists():
            print(f"⚠ File not found: {fp}")
            continue

        count = enrich_file(fp, apply=apply)
        total_enriched += count
        status = "✅ applied" if apply else "🔍 dry run"
        print(f"  {fp.name}: {count} cards enriched ({status})")

    print(f"\nTotal: {total_enriched} cards enriched")
    if not apply:
        print("Run with --apply to save changes.")


if __name__ == "__main__":
    main()
