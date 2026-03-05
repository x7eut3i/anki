"""Import/Export service: handles CSV, JSON, Excel, and .apkg file formats."""

import csv
import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from sqlmodel import Session, select, col

from app.models.card import Card
from app.models.deck import Deck
from app.models.category import Category
from app.services.dedup_service import DedupService, normalize_text
from app.config import get_settings

logger = logging.getLogger("anki.import_export")


class ImportExportService:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        self.user_id = user_id

    # ─── AI-Enhanced Import ───────────────────────────────────────────

    async def ai_import(
        self, raw_text: str, filename: str, deck_id: int,
        category_id: int | None = None,
    ) -> dict | None:
        """AI-enhanced import: send raw file content to AI for transformation.

        Handles ANY file format (custom columns, notes, etc.). AI analyses
        the content and returns proper card-schema objects.

        Returns ``None`` when AI is unavailable so the caller can fall back
        to the basic (column-mapping) import.
        """
        from app.services.ai_service import AIService

        ai = AIService(self.session, self.user_id)
        if not ai.is_available():
            logger.info("AI import: AI not available, falling back to basic import")
            return None  # Signal: fall back to basic import

        deck = self.session.get(Deck, deck_id)
        if not deck:
            raise ValueError("Deck not found")

        # Resolve selected category (if any)
        forced_category_name: str | None = None
        if category_id:
            cat_obj = self.session.get(Category, category_id)
            if cat_obj:
                forced_category_name = cat_obj.name

        logger.info(f"AI import: starting for file '{filename}', deck '{deck.name}', "
                     f"category={'<auto>' if not forced_category_name else forced_category_name}, "
                     f"content length={len(raw_text)} chars")

        # Available categories for classification
        cats = self.session.exec(select(Category)).all()
        cat_list = "、".join(c.name for c in cats)

        # ── Split content into batches (configurable) ───────────────
        settings = get_settings()
        MAX_BATCH_CHARS = settings.ai_import_batch_chars
        # Use per-user batch size from AI config if available
        from app.models.user import User
        from app.models.ai_config import AIConfig
        user = self.session.get(User, self.user_id)
        # Try AI config first, fall back to user setting, then app settings
        ai_config = self.session.exec(
            select(AIConfig).where(
                AIConfig.user_id == self.user_id,
                AIConfig.is_active == True
            )
        ).first()
        if ai_config and hasattr(ai_config, "import_batch_size") and ai_config.import_batch_size:
            ROWS_PER_BATCH = ai_config.import_batch_size
        elif user:
            ROWS_PER_BATCH = user.ai_import_batch_size
        else:
            ROWS_PER_BATCH = settings.ai_import_batch_rows
        logger.debug(f"AI import: batch config: max_chars={MAX_BATCH_CHARS}, max_rows={ROWS_PER_BATCH}")
        lines = raw_text.split("\n")
        header = lines[0] if lines else ""
        data_lines = lines[1:] if len(lines) > 1 else lines

        batches: list[list[str]] = []
        current_batch: list[str] = []
        current_size = len(header) + 1

        for line in data_lines:
            line_len = len(line) + 1
            if (
                current_batch
                and (current_size + line_len > MAX_BATCH_CHARS
                     or len(current_batch) >= ROWS_PER_BATCH)
            ):
                batches.append(current_batch)
                current_batch = []
                current_size = len(header) + 1
            current_batch.append(line)
            current_size += line_len

        if current_batch:
            batches.append(current_batch)

        if not batches:
            batches = [lines]
            header = ""

        # ── System prompt (static, cacheable) ───────────────────────
        from app.services.prompts import make_import_system_prompt, make_import_user_prompt, CARD_SYSTEM_PROMPT
        from app.services.prompt_loader import get_prompt

        # Load card_system prompt from DB (fallback to hardcoded)
        card_sys = get_prompt(self.session, "card_system", CARD_SYSTEM_PROMPT)

        if forced_category_name:
            system_prompt = card_sys + (
                f"\n\n═══ 可用分类列表 ═══\n"
                f"category字段从以下类别中选择最匹配的：{forced_category_name}\n"
            )
        else:
            system_prompt = card_sys + (
                f"\n\n═══ 可用分类列表 ═══\n"
                f"category字段从以下类别中选择最匹配的：{cat_list}\n"
            )

        # ── Process each batch (with retry, concurrently) ──────────
        all_cards: list[dict] = []
        errors: list[str] = []

        # Get max_retries and concurrency from AI config
        from app.models.ai_config import AIConfig
        ai_cfg = self.session.exec(
            select(AIConfig).where(AIConfig.is_enabled == True)
        ).first()
        max_retries = getattr(ai_cfg, "max_retries", 3) or 3
        import_concurrency = getattr(ai_cfg, "import_concurrency", 3) or 3

        logger.debug(f"AI import: processing {len(batches)} batch(es), "
                     f"max_retries={max_retries}, concurrency={import_concurrency}")

        import asyncio as _aio

        sem = _aio.Semaphore(import_concurrency)
        results_lock = _aio.Lock()

        async def _process_batch(i: int, batch: list[str]):
            batch_text = (
                (header + "\n" if header else "") + "\n".join(batch)
            )

            logger.debug(f"AI import: batch {i + 1}/{len(batches)}, "
                         f"{len(batch)} rows, {len(batch_text)} chars")

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": make_import_user_prompt(
                        filename=filename,
                        batch_text=batch_text,
                        category_list=cat_list,
                        forced_category=forced_category_name,
                    ),
                },
            ]

            batch_cards = None
            last_error = None

            async with sem:
                for attempt in range(max_retries):
                    try:
                        result = await ai.chat_completion(
                            messages, temperature=0.2, feature="import"
                        )
                        content = result["content"]
                        from app.services.json_repair import repair_json, robust_json_parse
                        content = repair_json(content)
                        parsed = robust_json_parse(content)
                        if parsed is None:
                            raise ValueError("AI返回的JSON格式错误，且修复失败")

                        if isinstance(parsed, dict):
                            batch_cards = parsed.get("cards", [])
                        elif isinstance(parsed, list):
                            batch_cards = parsed
                        else:
                            raise ValueError("AI返回的JSON格式不正确")

                        last_error = None
                        break
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(f"AI import: batch {i + 1} attempt {attempt + 1}/{max_retries} failed: {e}")
                        if attempt < max_retries - 1:
                            await _aio.sleep(2 * (attempt + 1))

            async with results_lock:
                if last_error or batch_cards is None:
                    logger.error(f"AI import: batch {i + 1} failed after {max_retries} retries: {last_error}")
                    errors.append(f"批次{i + 1}解析失败: {str(last_error)[:100]}")
                else:
                    all_cards.extend(batch_cards)
                    logger.debug(f"AI import: batch {i + 1} returned {len(batch_cards)} cards")

        # Launch all batch tasks concurrently (semaphore limits parallelism)
        batch_tasks = [_process_batch(i, batch) for i, batch in enumerate(batches)]
        await _aio.gather(*batch_tasks)

        if not all_cards:
            if errors:
                logger.warning(
                    "AI import: all batches failed, falling back: %s",
                    "; ".join(errors[:3]),
                )
                return None  # Signal: fall back to basic import
            return {"created": 0, "errors": errors, "ai_enhanced": True}

        logger.debug(f"AI import: total {len(all_cards)} cards parsed from AI")

        # ── Dedup & Save cards ───────────────────────────────────────
        created = 0
        skipped = 0

        # Build dedup index of existing cards for O(1) lookups
        existing_cards = self.session.exec(select(Card)).all()
        dedup_index: dict[str, int] = {}
        for ec in existing_cards:
            key = normalize_text(ec.front)
            if key:
                dedup_index[key] = ec.id

        for item in all_cards:
            try:
                front = (item.get("front") or "").strip()
                back = (item.get("back") or "").strip()
                if not front:
                    continue

                # Check for duplicate
                norm_front = normalize_text(front)
                if norm_front in dedup_index:
                    skipped += 1
                    continue

                # Resolve category
                cat_id = category_id  # Use user-selected category if provided
                if not cat_id:
                    cat_name = item.get("category", "")
                    if cat_name:
                        cat = self.session.exec(
                            select(Category).where(Category.name == cat_name)
                        ).first()
                        if cat:
                            cat_id = cat.id

                distractors = item.get("distractors", [])
                distractors_str = (
                    json.dumps(distractors, ensure_ascii=False)
                    if isinstance(distractors, list)
                    else str(distractors or "")
                )

                meta_info = item.get("meta_info", "")
                if isinstance(meta_info, dict):
                    meta_info = json.dumps(meta_info, ensure_ascii=False)

                card = Card(
                    deck_id=deck_id,
                    category_id=cat_id,
                    front=front,
                    back=back,
                    explanation=item.get("explanation", ""),
                    distractors=distractors_str,
                    tags=item.get("tags", ""),
                    meta_info=meta_info,
                    source=item.get("source", ""),
                    is_ai_generated=True,
                )
                self.session.add(card)
                created += 1
                # Add to dedup index so batch-internal dups are also caught
                dedup_index[norm_front] = -1
            except Exception as e:
                errors.append(f"保存失败: {str(e)[:100]}")

        deck.card_count += created
        self.session.add(deck)
        self.session.commit()

        skip_msg = f"，跳过重复 {skipped} 张" if skipped else ""
        logger.info(f"AI import: done — created={created}, skipped={skipped}, "
                     f"errors={len(errors)}, total_parsed={len(all_cards)}")
        return {
            "created": created,
            "skipped": skipped,
            "total_parsed": len(all_cards),
            "errors": errors,
            "ai_enhanced": True,
            "message": (
                f"AI 智能导入完成：解析 {len(all_cards)} 张，"
                f"成功导入 {created} 张{skip_msg}"
            ),
        }

    # ─── CSV Import/Export ────────────────────────────────────────────

    def export_csv(self, deck_id: int | None = None) -> str:
        """Export cards to CSV string with UTF-8 BOM for Excel compatibility."""
        from app.models.deck import Deck as DeckModel

        query = select(Card)
        if deck_id:
            query = query.where(Card.deck_id == deck_id)

        cards = self.session.exec(query).all()

        # Pre-load category and deck names
        cat_ids = list({c.category_id for c in cards if c.category_id})
        cat_map: dict[int, str] = {}
        if cat_ids:
            cat_rows = self.session.exec(select(Category).where(col(Category.id).in_(cat_ids))).all()
            cat_map = {cat.id: cat.name for cat in cat_rows}

        deck_ids = list({c.deck_id for c in cards})
        deck_map: dict[int, str] = {}
        if deck_ids:
            deck_rows = self.session.exec(select(DeckModel).where(col(DeckModel.id).in_(deck_ids))).all()
            deck_map = {d.id: d.name for d in deck_rows}

        output = io.StringIO()
        # Write UTF-8 BOM so Excel opens the file correctly
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow([
            "id", "deck", "category", "front", "back", "explanation",
            "distractors", "tags", "meta_info", "source",
            "is_ai_generated", "created_at", "updated_at",
        ])

        for card in cards:
            writer.writerow([
                card.id,
                deck_map.get(card.deck_id, ""),
                cat_map.get(card.category_id, "") if card.category_id else "",
                card.front,
                card.back,
                card.explanation,
                card.distractors,
                card.tags,
                card.meta_info,
                card.source,
                card.is_ai_generated,
                card.created_at.isoformat() if card.created_at else "",
                card.updated_at.isoformat() if card.updated_at else "",
            ])

        return output.getvalue()

    def import_csv(self, csv_content: str, deck_id: int) -> dict:
        """Import cards from CSV string."""
        deck = self.session.get(Deck, deck_id)
        if not deck:
            raise ValueError("Deck not found")

        # Build dedup index
        existing_cards = self.session.exec(select(Card)).all()
        dedup_index: dict[str, int] = {}
        for ec in existing_cards:
            key = normalize_text(ec.front)
            if key:
                dedup_index[key] = ec.id

        reader = csv.DictReader(io.StringIO(csv_content))
        created = 0
        skipped = 0
        errors = []

        for i, row in enumerate(reader):
            try:
                front = (row.get("front") or "").strip()
                if not front:
                    continue

                # Check for duplicate
                norm_front = normalize_text(front)
                if norm_front in dedup_index:
                    skipped += 1
                    continue

                # Find category
                cat_id = None
                if row.get("category"):
                    cat = self.session.exec(
                        select(Category).where(Category.name == row["category"])
                    ).first()
                    if cat:
                        cat_id = cat.id

                card = Card(
                    deck_id=deck_id,
                    category_id=cat_id,
                    front=front,
                    back=row.get("back", ""),
                    explanation=row.get("explanation", ""),
                    distractors=row.get("distractors", ""),
                    tags=row.get("tags", ""),
                    source=row.get("source", ""),
                )
                self.session.add(card)
                created += 1
                dedup_index[norm_front] = -1
            except Exception as e:
                errors.append(f"Row {i + 1}: {str(e)}")

        # Update deck card count
        deck.card_count += created
        self.session.add(deck)
        self.session.commit()

        return {"created": created, "skipped": skipped, "errors": errors}

    # ─── JSON Import/Export ───────────────────────────────────────────

    def export_json(self, deck_id: int | None = None) -> str:
        """Export cards to JSON string with all fields."""
        from app.models.deck import Deck as DeckModel

        query = select(Card)
        if deck_id:
            query = query.where(Card.deck_id == deck_id)

        cards = self.session.exec(query).all()

        # Pre-load category and deck names
        cat_ids = list({c.category_id for c in cards if c.category_id})
        cat_map: dict[int, str] = {}
        if cat_ids:
            cat_rows = self.session.exec(select(Category).where(col(Category.id).in_(cat_ids))).all()
            cat_map = {cat.id: cat.name for cat in cat_rows}

        deck_ids = list({c.deck_id for c in cards})
        deck_map: dict[int, str] = {}
        if deck_ids:
            deck_rows = self.session.exec(select(DeckModel).where(col(DeckModel.id).in_(deck_ids))).all()
            deck_map = {d.id: d.name for d in deck_rows}

        data = []
        for card in cards:
            # Parse distractors/meta_info as objects for cleaner JSON
            distractors = card.distractors
            try:
                distractors = json.loads(card.distractors) if card.distractors else []
            except (json.JSONDecodeError, TypeError):
                pass

            meta_info = card.meta_info
            try:
                meta_info = json.loads(card.meta_info) if card.meta_info else {}
            except (json.JSONDecodeError, TypeError):
                pass

            data.append({
                "id": card.id,
                "deck": deck_map.get(card.deck_id, ""),
                "category": cat_map.get(card.category_id, "") if card.category_id else "",
                "front": card.front,
                "back": card.back,
                "explanation": card.explanation,
                "distractors": distractors,
                "tags": card.tags,
                "meta_info": meta_info,
                "source": card.source,
                "is_ai_generated": card.is_ai_generated,
                "created_at": card.created_at.isoformat() if card.created_at else "",
                "updated_at": card.updated_at.isoformat() if card.updated_at else "",
            })

        return json.dumps(data, ensure_ascii=False, indent=2)

    def import_json(self, json_content: str, deck_id: int) -> dict:
        """Import cards from JSON string."""
        deck = self.session.get(Deck, deck_id)
        if not deck:
            raise ValueError("Deck not found")

        data = json.loads(json_content)
        if not isinstance(data, list):
            raise ValueError("JSON must be an array of card objects")

        created = 0
        skipped = 0
        errors = []

        # Build dedup index
        existing_cards = self.session.exec(select(Card)).all()
        dedup_index: dict[str, int] = {}
        for ec in existing_cards:
            key = normalize_text(ec.front)
            if key:
                dedup_index[key] = ec.id

        for i, item in enumerate(data):
            try:
                front = (item.get("front") or "").strip()
                if not front:
                    continue

                # Check for duplicate
                norm_front = normalize_text(front)
                if norm_front in dedup_index:
                    skipped += 1
                    continue

                cat_id = None
                if item.get("category"):
                    cat = self.session.exec(
                        select(Category).where(Category.name == item["category"])
                    ).first()
                    if cat:
                        cat_id = cat.id

                card = Card(
                    deck_id=deck_id,
                    category_id=cat_id,
                    front=item.get("front", ""),
                    back=item.get("back", ""),
                    explanation=item.get("explanation", ""),
                    distractors=item.get("distractors", "") if isinstance(item.get("distractors"), str) else json.dumps(item.get("distractors", "")),
                    tags=item.get("tags", ""),
                    source=item.get("source", ""),
                )
                self.session.add(card)
                created += 1
                dedup_index[norm_front] = -1
            except Exception as e:
                errors.append(f"Item {i}: {str(e)}")

        deck.card_count += created
        self.session.add(deck)
        self.session.commit()

        return {"created": created, "skipped": skipped, "errors": errors}

    # ─── Excel Import ──────────────────────────────────────────────────

    def import_excel(self, file_bytes: bytes, deck_id: int) -> dict:
        """Import cards from an Excel (.xlsx) file."""
        import openpyxl

        deck = self.session.get(Deck, deck_id)
        if not deck:
            raise ValueError("Deck not found")

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            raise ValueError("Excel file has no active sheet")

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {"created": 0, "errors": ["Empty file"]}

        # First row as header; normalize to lowercase stripped strings
        raw_header = rows[0]
        header = [str(h).strip().lower() if h else f"col_{i}" for i, h in enumerate(raw_header)]

        # Map common column names to card fields
        FIELD_ALIASES = {
            "front": ["front", "题目", "问题", "question", "题干"],
            "back": ["back", "答案", "answer", "正确答案", "correct_answer"],
            "explanation": ["explanation", "解析", "解释", "说明"],
            "distractors": ["distractors", "干扰项", "错误选项", "wrong_answers"],
            "tags": ["tags", "标签", "tag"],
            "category": ["category", "分类", "类别", "科目"],
            "source": ["source", "来源", "出处"],
        }

        col_map: dict[str, int] = {}
        for field, aliases in FIELD_ALIASES.items():
            for i, h in enumerate(header):
                if h in aliases:
                    col_map[field] = i
                    break

        if "front" not in col_map:
            # Fallback: first col = front, second = back
            col_map["front"] = 0
            if len(header) > 1:
                col_map["back"] = 1
            if len(header) > 2:
                col_map["explanation"] = 2

        created = 0
        skipped = 0
        errors = []

        # Build dedup index
        existing_cards = self.session.exec(select(Card)).all()
        dedup_index: dict[str, int] = {}
        for ec in existing_cards:
            key = normalize_text(ec.front)
            if key:
                dedup_index[key] = ec.id

        for row_num, row in enumerate(rows[1:], start=2):
            try:
                def get_val(field: str, default: str = "") -> str:
                    idx = col_map.get(field)
                    if idx is not None and idx < len(row) and row[idx] is not None:
                        return str(row[idx]).strip()
                    return default

                front = get_val("front")
                if not front:
                    continue

                # Check for duplicate
                norm_front = normalize_text(front)
                if norm_front in dedup_index:
                    skipped += 1
                    continue

                cat_id = None
                cat_name = get_val("category")
                if cat_name:
                    cat = self.session.exec(
                        select(Category).where(Category.name == cat_name)
                    ).first()
                    if cat:
                        cat_id = cat.id

                distractors_raw = get_val("distractors")
                if distractors_raw:
                    try:
                        parsed = json.loads(distractors_raw)
                        if isinstance(parsed, list):
                            distractors_raw = json.dumps(parsed, ensure_ascii=False)
                    except json.JSONDecodeError:
                        # Treat as comma-separated
                        items = [x.strip() for x in distractors_raw.split(",") if x.strip()]
                        distractors_raw = json.dumps(items, ensure_ascii=False)

                card = Card(
                    deck_id=deck_id,
                    category_id=cat_id,
                    front=front,
                    back=get_val("back"),
                    explanation=get_val("explanation"),
                    distractors=distractors_raw,
                    tags=get_val("tags"),
                    source=get_val("source"),
                )
                self.session.add(card)
                created += 1
                dedup_index[norm_front] = -1
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")

        deck.card_count += created
        self.session.add(deck)
        self.session.commit()
        wb.close()

        return {"created": created, "skipped": skipped, "errors": errors}

    # ─── Anki .apkg Import ────────────────────────────────────────────

    def import_apkg(self, file_bytes: bytes, deck_name: str) -> dict:
        """Import cards from an Anki .apkg file (ZIP with SQLite inside)."""
        import sqlite3
        import tempfile
        import os

        created = 0
        errors = []

        try:
            # .apkg is a ZIP file
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                # Find the SQLite database
                db_name = None
                for name in zf.namelist():
                    if name in ("collection.anki2", "collection.anki21"):
                        db_name = name
                        break

                if not db_name:
                    raise ValueError("Invalid .apkg file: no collection database found")

                # Extract to temp file
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp.write(zf.read(db_name))
                    tmp_path = tmp.name

            # Read the Anki SQLite database
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Create deck
            deck = Deck(
                name=deck_name,
                description=f"Imported from Anki .apkg",
            )
            self.session.add(deck)
            self.session.commit()
            self.session.refresh(deck)

            # Build dedup index
            existing_cards = self.session.exec(select(Card)).all()
            dedup_index: dict[str, int] = {}
            for ec in existing_cards:
                key = normalize_text(ec.front)
                if key:
                    dedup_index[key] = ec.id

            skipped = 0

            # Read notes (Anki stores content in 'notes' table)
            try:
                cursor.execute("SELECT flds, tags FROM notes")
                for row in cursor.fetchall():
                    fields = row["flds"].split("\x1f")  # Anki field separator
                    if len(fields) >= 2:
                        front = fields[0].strip()
                        norm_front = normalize_text(front)
                        if norm_front in dedup_index:
                            skipped += 1
                            continue
                        card = Card(
                            deck_id=deck.id,
                            front=front,
                            back=fields[1],
                            explanation=fields[2] if len(fields) > 2 else "",
                            tags=row["tags"].strip(),
                        )
                        self.session.add(card)
                        created += 1
                        dedup_index[norm_front] = -1
            except sqlite3.OperationalError as e:
                errors.append(f"DB read error: {str(e)}")

            conn.close()
            os.unlink(tmp_path)

            deck.card_count = created
            self.session.add(deck)
            self.session.commit()

        except zipfile.BadZipFile:
            raise ValueError("Invalid .apkg file: not a valid ZIP archive")
        except Exception as e:
            errors.append(str(e))

        return {"created": created, "skipped": skipped, "deck_id": deck.id if deck else None, "errors": errors}
