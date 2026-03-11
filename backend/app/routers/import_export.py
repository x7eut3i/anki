import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from sqlmodel import Session

from app.auth import get_current_user
from app.database import get_session, engine
from app.models.user import User
from app.services.import_export_service import ImportExportService
from app.routers.ai_jobs import create_job, update_job_status, is_job_cancelled

logger = logging.getLogger("anki.import_export")

router = APIRouter(prefix="/api/import-export", tags=["import-export"])


def _run_async(coro):
    """Run an async coroutine in a new event loop (for background threads)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _bg_ai_import(
    job_id: int, user_id: int, deck_id: int, content_text: str,
    filename: str, category_id: int | None, file_bytes: bytes | None = None,
    allow_correction: bool = False,
):
    """Background task for AI-enhanced import (CSV/JSON/Excel)."""
    from sqlmodel import Session as SyncSession
    import json as _json

    update_job_status(job_id, "running", progress=10)

    try:
        with SyncSession(engine) as session:
            if is_job_cancelled(job_id):
                return
            service = ImportExportService(session, user_id)

            # Try AI import
            if is_job_cancelled(job_id):
                return
            update_job_status(job_id, "running", progress=20)
            ai_result = None
            try:
                ai_result = _run_async(service.ai_import(
                    content_text, filename, deck_id,
                    category_id=category_id,
                    allow_correction=allow_correction,
                ))
            except Exception as e:
                logger.warning("BG AI import failed, falling back: %s", e)
                ai_result = None

            if ai_result is not None:
                count = ai_result.get("created", 0) or ai_result.get("imported", 0)
                msg = ai_result.get("message", f"AI 导入完成：{count} 张卡片")
                update_job_status(
                    job_id, "completed",
                    result_json=_json.dumps({
                        "created": count,
                        "ai_enhanced": True,
                        "message": msg,
                    }, ensure_ascii=False),
                )
                return

            # Fallback to basic import
            update_job_status(job_id, "running", progress=60)
            try:
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if ext == "csv":
                    result = service.import_csv(content_text, deck_id)
                elif ext in ("json",):
                    result = service.import_json(content_text, deck_id)
                elif ext in ("xlsx", "xls") and file_bytes:
                    result = service.import_excel(file_bytes, deck_id)
                else:
                    result = service.import_csv(content_text, deck_id)  # default

                count = result.get("imported", 0) or result.get("created", 0)
                msg = result.get("message", f"基础导入完成：{count} 张卡片")
                update_job_status(
                    job_id, "completed",
                    result_json=_json.dumps({
                        "created": count,
                        "ai_enhanced": False,
                        "message": msg,
                    }, ensure_ascii=False),
                )
            except Exception as e:
                update_job_status(job_id, "failed", error_message=f"导入失败: {str(e)[:2000]}")

    except Exception as e:
        logger.error("BG AI import error: %s", e, exc_info=True)
        update_job_status(job_id, "failed", error_message=str(e)[:2000])


@router.get("/export/csv")
def export_csv(
    deck_id: int | None = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = ImportExportService(session, current_user.id)
    csv_str = service.export_csv(deck_id=deck_id)
    return PlainTextResponse(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=flashcards.csv"},
    )


@router.get("/export/json")
def export_json(
    deck_id: int | None = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    service = ImportExportService(session, current_user.id)
    json_str = service.export_json(deck_id=deck_id)
    return PlainTextResponse(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=flashcards.json"},
    )


@router.post("/import/csv")
async def import_csv(
    deck_id: int,
    category_id: int | None = None,
    allow_correction: bool = False,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    content = (await file.read()).decode("utf-8")
    filename = file.filename or "upload.csv"
    job = create_job(session, current_user.id, "import", f"导入: {filename}")
    background_tasks.add_task(
        _bg_ai_import, job.id, current_user.id, deck_id, content, filename, category_id,
        allow_correction=allow_correction,
    )
    return {"job_id": job.id, "message": f"导入任务已提交，后台处理中"}


@router.post("/import/json")
async def import_json(
    deck_id: int,
    category_id: int | None = None,
    allow_correction: bool = False,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    content = (await file.read()).decode("utf-8")
    filename = file.filename or "upload.json"
    job = create_job(session, current_user.id, "import", f"导入: {filename}")
    background_tasks.add_task(
        _bg_ai_import, job.id, current_user.id, deck_id, content, filename, category_id,
        allow_correction=allow_correction,
    )
    return {"job_id": job.id, "message": f"导入任务已提交，后台处理中"}


@router.post("/import/apkg")
async def import_apkg(
    deck_name: str = "Imported Deck",
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    file_bytes = await file.read()
    service = ImportExportService(session, current_user.id)
    try:
        result = service.import_apkg(file_bytes, deck_name)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import/excel")
async def import_excel(
    deck_id: int,
    category_id: int | None = None,
    allow_correction: bool = False,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Import cards from an Excel (.xlsx) file with AI enhancement."""
    file_bytes = await file.read()
    filename = file.filename or "upload.xlsx"

    # Convert Excel to text for AI processing
    content_text = ""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(
            __import__("io").BytesIO(file_bytes), read_only=True, data_only=True
        )
        ws = wb.active
        if ws:
            rows = list(ws.iter_rows(values_only=True))
            content_text = "\n".join(
                "\t".join(str(c) if c else "" for c in row) for row in rows
            )
        wb.close()
    except Exception as e:
        logger.warning("Excel parse for text failed: %s", e)

    job = create_job(session, current_user.id, "import", f"导入: {filename}")
    background_tasks.add_task(
        _bg_ai_import, job.id, current_user.id, deck_id, content_text, filename, category_id, file_bytes,
        allow_correction=allow_correction,
    )
    return {"job_id": job.id, "message": f"导入任务已提交，后台处理中"}


@router.post("/import/direct")
async def import_direct(
    deck_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Direct import: import JSON file matching export format, NO AI processing.

    Accepts a JSON file with a cards array. Each card object should have:
    - front (required)
    - back (required)
    - explanation, distractors (array), tags, meta_info (object), category, etc.
    """
    import json as _json
    from app.models.card import Card
    from app.models.deck import Deck
    from app.models.category import Category
    from app.services.dedup_service import DedupService

    content = (await file.read()).decode("utf-8")

    try:
        data = _json.loads(content)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON文件格式")

    # Accept both {"cards": [...]} and [...]
    if isinstance(data, dict):
        cards_list = data.get("cards", data.get("items", []))
    elif isinstance(data, list):
        cards_list = data
    else:
        raise HTTPException(status_code=400, detail="JSON必须是数组或包含cards字段的对象")

    if not cards_list:
        raise HTTPException(status_code=400, detail="没有找到卡片数据")

    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="牌组不存在")

    # Load categories for mapping
    from sqlmodel import select as _sel
    cats = session.exec(_sel(Category)).all()
    cat_map = {c.name: c for c in cats}

    dedup = DedupService(session, current_user.id)
    imported = 0
    skipped = 0

    for card_data in cards_list:
        front = card_data.get("front", "").strip()
        back = card_data.get("back", "").strip()
        if not front or not back:
            skipped += 1
            continue

        # Dedup check
        if dedup.find_duplicate(front):
            skipped += 1
            continue

        # Process distractors
        distractors = card_data.get("distractors", "")
        if isinstance(distractors, list):
            distractors = _json.dumps(distractors, ensure_ascii=False)

        # Process meta_info
        meta_info = card_data.get("meta_info", "")
        if isinstance(meta_info, dict):
            meta_info = _json.dumps(meta_info, ensure_ascii=False)

        # Resolve category
        cat_name = card_data.get("category", card_data.get("category_name", ""))
        category = cat_map.get(cat_name) if cat_name else None

        # Preserve is_ai_generated if present in export
        is_ai_gen = card_data.get("is_ai_generated", False)
        if isinstance(is_ai_gen, str):
            is_ai_gen = is_ai_gen.lower() in ("true", "1", "yes")

        card = Card(
            deck_id=deck.id,
            category_id=category.id if category else deck.category_id,
            front=front,
            back=back,
            explanation=card_data.get("explanation", ""),
            distractors=distractors,
            tags=card_data.get("tags", ""),
            meta_info=meta_info,
            source=card_data.get("source", ""),
            is_ai_generated=bool(is_ai_gen),
        )
        session.add(card)
        imported += 1

    # Update deck count
    deck.card_count = (deck.card_count or 0) + imported
    session.add(deck)
    session.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "message": f"直接导入完成：{imported} 张卡片已导入，{skipped} 张跳过",
    }