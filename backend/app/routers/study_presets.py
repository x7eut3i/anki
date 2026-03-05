import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models.study_preset import StudyPreset
from app.models.user import User

logger = logging.getLogger("anki.study_presets")

router = APIRouter(prefix="/api/study-presets", tags=["study-presets"])


class PresetCreate(BaseModel):
    name: str
    icon: str = "📋"
    category_ids: list[int] = []
    deck_ids: list[int] = []
    card_count: int = 20


class PresetUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    category_ids: list[int] | None = None
    deck_ids: list[int] | None = None
    card_count: int | None = None
    sort_order: int | None = None


@router.get("")
def list_presets(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    presets = session.exec(
        select(StudyPreset)
        .where(StudyPreset.user_id == current_user.id)
        .order_by(StudyPreset.sort_order, StudyPreset.id)
    ).all()

    result = []
    for p in presets:
        d = p.model_dump()
        d["category_ids"] = json.loads(p.category_ids or "[]")
        d["deck_ids"] = json.loads(p.deck_ids or "[]")
        result.append(d)
    return {"presets": result}


@router.post("")
def create_preset(
    data: PresetCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    preset = StudyPreset(
        user_id=current_user.id,
        name=data.name,
        icon=data.icon,
        category_ids=json.dumps(data.category_ids),
        deck_ids=json.dumps(data.deck_ids),
        card_count=data.card_count,
    )
    session.add(preset)
    session.commit()
    session.refresh(preset)
    d = preset.model_dump()
    d["category_ids"] = data.category_ids
    d["deck_ids"] = data.deck_ids
    return d


@router.put("/{preset_id}")
def update_preset(
    preset_id: int,
    data: PresetUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    preset = session.get(StudyPreset, preset_id)
    if not preset or preset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Preset not found")

    if data.name is not None:
        preset.name = data.name
    if data.icon is not None:
        preset.icon = data.icon
    if data.category_ids is not None:
        preset.category_ids = json.dumps(data.category_ids)
    if data.deck_ids is not None:
        preset.deck_ids = json.dumps(data.deck_ids)
    if data.card_count is not None:
        preset.card_count = data.card_count
    if data.sort_order is not None:
        preset.sort_order = data.sort_order

    from datetime import datetime, timezone
    preset.updated_at = datetime.now(timezone.utc)
    session.add(preset)
    session.commit()
    session.refresh(preset)
    d = preset.model_dump()
    d["category_ids"] = json.loads(preset.category_ids or "[]")
    d["deck_ids"] = json.loads(preset.deck_ids or "[]")
    return d


@router.delete("/{preset_id}")
def delete_preset(
    preset_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    preset = session.get(StudyPreset, preset_id)
    if not preset or preset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Preset not found")
    session.delete(preset)
    session.commit()
    return {"ok": True}
