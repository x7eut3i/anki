from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


# Default categories (consolidated from 20 to 12)
DEFAULT_CATEGORIES = [
    {"name": "成语", "description": "成语含义、用法、易错点", "icon": "📝", "sort_order": 1},
    {"name": "实词辨析", "description": "近义词对比、区别、语境", "icon": "📖", "sort_order": 2},
    {"name": "规范词与公文", "description": "公文用语、规范表达、文种格式", "icon": "📋", "sort_order": 3},
    {"name": "时政与重要论述", "description": "时事政治、重要会议、领导人讲话", "icon": "🔥", "sort_order": 4},
    {"name": "常识判断", "description": "法律、经济、地理、科技、生活常识", "icon": "💡", "sort_order": 5},
    {"name": "政治理论与哲学", "description": "马克思主义、中特理论、哲学原理", "icon": "🏛️", "sort_order": 6},
    {"name": "历史文化与党史", "description": "中国历史、文化常识、党史事件", "icon": "🏯", "sort_order": 7},
    {"name": "逻辑与数量", "description": "逻辑推理、数量关系、资料分析", "icon": "🧩", "sort_order": 8},
    {"name": "申论素材", "description": "金句名言、论点、范文段落", "icon": "✍️", "sort_order": 9},
    {"name": "古诗词名句", "description": "诗句、作者、出处、含义", "icon": "🎋", "sort_order": 10},
]


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=50)
    description: str = Field(default="", max_length=500)
    icon: str = Field(default="📝", max_length=10)
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Per-category study settings (user can override)
    default_new_per_day: int = Field(default=10)
    default_reviews_per_day: int = Field(default=50)
