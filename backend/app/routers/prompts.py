"""Router for prompt configuration management (Prompt管理)."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models.prompt_config import PromptConfig
from app.models.user import User

logger = logging.getLogger("anki.prompts")

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


# ── Default prompts (seeded on first access) ──

def _get_default_prompts() -> list[dict]:
    """Return the default prompt definitions."""
    from app.services.prompts import CARD_SYSTEM_PROMPT, ARTICLE_ANALYSIS_SYSTEM_PROMPT

    return [
        {
            "prompt_key": "card_system",
            "display_name": "卡片生成 - 系统提示词",
            "description": "用于：① 文章精读→生成卡片 ② 每日自动抓取文章→生成卡片 ③ 导入/导出→AI导入。控制AI如何根据内容类型生成学习卡片（成语、时政、法律等各类题型格式）。",
            "content": CARD_SYSTEM_PROMPT,
        },
        {
            "prompt_key": "article_analysis",
            "display_name": "文章精读 - 系统提示词",
            "description": "用于：精读文章页面点击「深度分析」时的AI系统提示词。控制AI如何对文章进行深度精读分析，生成高亮标注、考点分析、申论指导等结构化内容。",
            "content": ARTICLE_ANALYSIS_SYSTEM_PROMPT,
        },
        {
            "prompt_key": "batch_enrich",
            "display_name": "卡片补充 - 系统提示词",
            "description": "用于：卡组管理页面「批量补充」按钮。控制AI如何为缺少干扰项或知识点信息的卡片补充内容。",
            "content": (
                "你是出题专家。请为以下卡片补充缺失的信息。\n"
                "对于needs_distractors=true的卡片，生成3个合理的干扰项(distractors)。\n"
                "对于needs_meta=true的卡片，生成meta_info，包含：\n"
                '  - knowledge: {key_points, synonyms, antonyms, related, memory_tips, golden_quotes, formal_terms, essay_material}\n'
                '  - exam_focus: {difficulty: "easy/medium/hard", frequency: "high/medium/low"}\n'
                '  - facts: {关键事实}\n'
                '注意：meta_info中不要包含distractors字段，干扰项只放在顶层distractors字段中。\n\n'
                "回复JSON数组格式，每项包含card_id和补充的字段:\n"
                '[{"card_id": 1, "distractors": ["A","B","C"], "meta_info": {...}}, ...]'
            ),
        },
{
            "prompt_key": "card_from_selection",
            "display_name": "划词制卡 - 系统提示词",
            "description": "用于：精读文章页面→选中文字后点击「生成卡片」按钮。控制AI如何根据文章中选中的文字片段生成一张独立可读的学习卡片。",
            "content": (
                "你是一位资深公务员考试辅导专家（行测+申论双科），同时也是学习卡片设计专家。\n"
                "你的任务：根据用户在文章中选中的文字片段，生成一张高质量的学习卡片。\n\n"
                "═══ 核心原则 ═══\n"
                "1. 卡片必须独立可读，不得引用原文上下文（不说\"根据文章\"\"文中提到\"等）\n"
                "2. 充分利用选中文本包含的知识，提炼出有考试价值的知识点\n"
                "3. 根据选中内容自动判断最适合的卡片类型（成语、时政、法律、金句等）\n"
                "4. 如有文章上下文，利用它补充背景信息到explanation中\n\n"
                "═══ 根据内容类型选择卡片格式 ═══\n"
                "【成语】front=成语本身(4字), back=正确释义+拼音, distractors=3个错误释义\n"
                "【实词辨析】front=语境句(含横线), back=正确词语, distractors=3个近义词\n"
                "【规范词】front=口语说法, back=公文规范表述, distractors=3个错误表述\n"
                "【金句/名言】front=挖空的金句, back=关键词, distractors=3个错误填空\n"
                "【时政热点】front=独立知识问题, back=准确答案, distractors=3个错误答案\n"
                "【法律常识】front=法律情景题, back=正确答案(含法条), distractors=3个错误解读\n"
                "【申论素材】front=论点问题, back=核心论点, distractors=3个偏题论点\n"
                "【古诗词】front=诗句填空, back=答案, distractors=3个错误填充\n\n"
                "═══ JSON格式要求 ═══\n"
                "返回一个JSON对象（不是数组），包含：\n"
                "{\n"
                '  "front": "题面/问题",\n'
                '  "back": "正确答案",\n'
                '  "explanation": "详细解析（不少于50字，包含知识背景、易错点、记忆方法）",\n'
                '  "distractors": ["错误答案1", "错误答案2", "错误答案3"],\n'
                '  "tags": "标签1,标签2",\n'
                '  "category": "最匹配的科目分类名",\n'
                '  "meta_info": {\n'
                '    "knowledge": { "key_points": [], "related": [], "memory_tips": "" },\n'
                '    "exam_focus": { "difficulty": "easy|medium|hard", "frequency": "high|medium|low" }\n'
                "  }\n"
                "}\n\n"
                "═══ 绝对规则 ═══\n"
                "1. 必须有恰好3个distractors，不能为空\n"
                "2. distractors是错误的答案/释义，不是题目名\n"
                "3. front独立可读，不引用原文\n"
                "4. back是正确答案的完整文本，不是选项字母\n"
                "5. explanation是知识性解析，包含背景和记忆方法\n"
                "6. 只输出JSON对象，不要markdown代码块标记\n"
                "7. 生僻字/多音字用括号标注拼音"
            ),
        },
    ]


def sync_default_prompts():
    """Sync non-customized prompts with code defaults on startup.

    If a prompt in the DB has is_customized=False but its content differs from
    the current code default, update it. Also seeds any new prompts that don't
    exist in the DB yet.
    """
    from app.database import engine

    defaults = {p["prompt_key"]: p for p in _get_default_prompts()}

    with Session(engine) as session:
        existing = session.exec(select(PromptConfig)).all()
        existing_keys = {p.prompt_key for p in existing}

        updated = 0
        added = 0

        for p in existing:
            if p.prompt_key in defaults and not p.is_customized:
                default_content = defaults[p.prompt_key]["content"]
                if p.content != default_content:
                    p.content = default_content
                    p.description = defaults[p.prompt_key].get("description", p.description)
                    p.updated_at = datetime.now(timezone.utc)
                    session.add(p)
                    updated += 1
                    logger.info("🔄 Updated prompt '%s' to latest default", p.prompt_key)

        # Seed any new prompts not yet in DB
        for key, pdata in defaults.items():
            if key not in existing_keys:
                pc = PromptConfig(**pdata)
                session.add(pc)
                added += 1
                logger.info("➕ Added new prompt '%s'", key)

        if updated or added:
            session.commit()
            logger.info("✅ Prompt sync: %d updated, %d added", updated, added)
        else:
            logger.debug("✅ Prompts already up to date")


# ── Schemas ──

class PromptResponse(BaseModel):
    id: int
    prompt_key: str
    display_name: str
    description: str
    content: str
    model_override: str
    is_customized: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptUpdate(BaseModel):
    content: str | None = None
    model_override: str | None = None


# ── Endpoints ──

@router.get("", response_model=list[PromptResponse])
def list_prompts(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List all prompt configs. Seeds defaults if table is empty."""
    prompts = session.exec(select(PromptConfig).order_by(PromptConfig.id)).all()

    if not prompts:
        # Seed default prompts
        for p in _get_default_prompts():
            pc = PromptConfig(**p)
            session.add(pc)
        session.commit()
        prompts = session.exec(select(PromptConfig).order_by(PromptConfig.id)).all()

    return [PromptResponse.model_validate(p) for p in prompts]


@router.get("/{prompt_key}", response_model=PromptResponse)
def get_prompt(
    prompt_key: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get a specific prompt by key."""
    prompt = session.exec(
        select(PromptConfig).where(PromptConfig.prompt_key == prompt_key)
    ).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt不存在")
    return PromptResponse.model_validate(prompt)


@router.put("/{prompt_key}", response_model=PromptResponse)
def update_prompt(
    prompt_key: str,
    data: PromptUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update a prompt's content and/or model override."""
    prompt = session.exec(
        select(PromptConfig).where(PromptConfig.prompt_key == prompt_key)
    ).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt不存在")

    if data.content is not None:
        prompt.content = data.content
        prompt.is_customized = True
    if data.model_override is not None:
        prompt.model_override = data.model_override

    prompt.updated_at = datetime.now(timezone.utc)
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return PromptResponse.model_validate(prompt)


@router.post("/{prompt_key}/reset", response_model=PromptResponse)
def reset_prompt(
    prompt_key: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Reset a prompt to its default content."""
    prompt = session.exec(
        select(PromptConfig).where(PromptConfig.prompt_key == prompt_key)
    ).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt不存在")

    defaults = {p["prompt_key"]: p["content"] for p in _get_default_prompts()}
    if prompt_key in defaults:
        prompt.content = defaults[prompt_key]
        prompt.is_customized = False
        prompt.updated_at = datetime.now(timezone.utc)
        session.add(prompt)
        session.commit()
        session.refresh(prompt)

    return PromptResponse.model_validate(prompt)
