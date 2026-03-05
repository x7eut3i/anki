"""Shared test fixtures for the flashcard app."""

import json
import os
import pytest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool

# Force test database before importing app
os.environ["DATABASE_URL"] = "sqlite:///test.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"

from app.main import app
from app.database import get_session
from app.auth import hash_password, create_access_token
from app.models.user import User
from app.models.category import Category, DEFAULT_CATEGORIES
from app.models.deck import Deck
from app.models.card import Card
from app.models.review_log import ReviewLog
from app.models.study_session import StudySession
from app.models.ai_config import AIConfig, AIUsageLog
from app.models.user_card_progress import UserCardProgress


# ── AI config loaded dynamically from ai_config.json ──
AI_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "ai_config.json"


def load_ai_config() -> dict:
    """Load AI configuration from ai_config.json at project root."""
    if AI_CONFIG_PATH.exists():
        with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "api_base_url": data.get("api_base_url", ""),
            "api_key": data.get("api_key", ""),
            "model": data.get("model", ""),
            "max_daily_calls": data.get("max_daily_calls", 100),
        }
    return {
        "api_base_url": "https://api.example.com/v1",
        "api_key": "sk-test-placeholder",
        "model": "test-model",
        "max_daily_calls": 100,
    }


# In-memory SQLite for tests
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(name="session")
def session_fixture():
    """Create a fresh in-memory DB session for each test."""
    SQLModel.metadata.create_all(TEST_ENGINE)
    with Session(TEST_ENGINE) as session:
        yield session
    SQLModel.metadata.drop_all(TEST_ENGINE)


@pytest.fixture(name="client")
def client_fixture(session: Session):
    """Create a test client with overridden DB session."""

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="test_user")
def test_user_fixture(session: Session) -> User:
    """Create a test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("testpassword"),
        is_admin=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture(name="admin_user")
def admin_user_fixture(session: Session) -> User:
    """Create an admin user."""
    user = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("adminpassword"),
        is_admin=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture(name="auth_headers")
def auth_headers_fixture(test_user: User) -> dict:
    """Create auth headers for test user."""
    token = create_access_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(name="admin_headers")
def admin_headers_fixture(admin_user: User) -> dict:
    """Create auth headers for admin user."""
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(name="categories")
def categories_fixture(session: Session) -> list[Category]:
    """Seed default categories."""
    cats = []
    for cat_data in DEFAULT_CATEGORIES:
        cat = Category(**cat_data)
        session.add(cat)
        cats.append(cat)
    session.commit()
    for cat in cats:
        session.refresh(cat)
    return cats


@pytest.fixture(name="test_deck")
def test_deck_fixture(session: Session, test_user: User, categories: list[Category]) -> Deck:
    """Create a test deck."""
    deck = Deck(
        name="测试牌组",
        description="Test deck",
        category_id=categories[0].id,
    )
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


@pytest.fixture(name="sample_cards")
def sample_cards_fixture(
    session: Session, test_user: User, test_deck: Deck, categories: list[Category]
) -> list[Card]:
    """Create sample cards across categories."""
    cards_data = [
        {
            "front": "画蛇添足的含义是什么？",
            "back": "比喻做多余的事，反而不恰当",
            "category_id": categories[0].id,  # 成语
        },
        {
            "front": "'截止'和'截至'的区别是什么？",
            "back": "'截止'表示到某个时间停止；'截至'表示到某个时间为止（后面还可能继续）",
            "category_id": categories[1].id,  # 实词辨析
        },
        {
            "front": "我国的根本政治制度是什么？",
            "back": "人民代表大会制度",
            "distractors": '["政治协商制度","民族区域自治制度","基层群众自治制度"]',
            "category_id": categories[4].id,  # 常识判断
        },
        {
            "front": "中华人民共和国成立于___年___月___日",
            "back": "1949年10月1日",
            "category_id": categories[6].id,  # 历史文化
        },
        {
            "front": "GDP是指什么？它的作用是什么？",
            "back": "GDP是指国内生产总值，是衡量一个国家经济规模的重要指标",
            "category_id": categories[8].id,  # 申论素材
        },
    ]

    cards = []
    for data in cards_data:
        card = Card(
            deck_id=test_deck.id,
            **data,
        )
        session.add(card)
        cards.append(card)

    test_deck.card_count = len(cards)
    session.add(test_deck)
    session.commit()
    for card in cards:
        session.refresh(card)

    return cards


@pytest.fixture(name="ai_config")
def ai_config_fixture() -> dict:
    """Load AI config dynamically from ai_config.json."""
    return load_ai_config()


@pytest.fixture(name="ai_config_db")
def ai_config_db_fixture(session: Session, test_user: User, ai_config: dict) -> AIConfig:
    """Create an AIConfig record in the test DB using values from ai_config.json."""
    config = AIConfig(
        user_id=test_user.id,
        api_base_url=ai_config["api_base_url"],
        api_key=ai_config["api_key"],
        model=ai_config["model"],
        max_daily_calls=ai_config["max_daily_calls"],
        is_enabled=True,
    )
    session.add(config)
    session.commit()
    session.refresh(config)
    return config
