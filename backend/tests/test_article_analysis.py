"""Tests for article analysis (文章精读) endpoints."""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.article_analysis import ArticleAnalysis
from app.models.ai_config import AIConfig
from app.models.user import User


# ── Fixtures ──

@pytest.fixture(name="sample_analysis")
def sample_analysis_fixture(session: Session, test_user: User) -> ArticleAnalysis:
    """Create a sample article analysis."""
    analysis = ArticleAnalysis(
        user_id=test_user.id,
        title="关于推进高质量发展的意见",
        source_url="https://example.com/article1",
        source_name="人民日报",
        publish_date="2024-01-15",
        content="这是一篇关于高质量发展的文章全文内容。" * 20,
        analysis_html="<section><h3>分析</h3><p>内容</p></section>",
        analysis_json=json.dumps({
            "summary": "文章概述高质量发展的路径",
            "quality_score": 8,
            "quality_reason": "具有很强的考试价值",
            "highlights": [
                {
                    "text": "高质量发展",
                    "type": "key_point",
                    "color": "red",
                    "annotation": "核心概念",
                }
            ],
            "overall_analysis": {
                "theme": "高质量发展",
                "structure": "总分总",
                "core_arguments": ["论点一", "论点二"],
            },
            "exam_points": {
                "essay_angles": ["从经济角度分析"],
                "formal_terms": ["新发展理念"],
            },
            "vocabulary": [
                {"term": "新质生产力", "explanation": "以创新为主导的先进生产力"}
            ],
            "reading_notes": "这篇文章适合作为申论素材积累。",
        }, ensure_ascii=False),
        quality_score=8,
        quality_reason="具有很强的考试价值",
        word_count=400,
        status="new",
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)
    return analysis


@pytest.fixture(name="multiple_analyses")
def multiple_analyses_fixture(session: Session, test_user: User) -> list[ArticleAnalysis]:
    """Create multiple article analyses for testing filters."""
    items = []
    data = [
        {"title": "文章A", "quality_score": 9, "status": "new", "is_starred": True},
        {"title": "文章B", "quality_score": 7, "status": "reading", "is_starred": False},
        {"title": "文章C", "quality_score": 5, "status": "finished", "is_starred": True},
        {"title": "文章D", "quality_score": 3, "status": "new", "is_starred": False},
    ]
    for d in data:
        item = ArticleAnalysis(
            user_id=test_user.id,
            title=d["title"],
            content="内容" * 50,
            quality_score=d["quality_score"],
            status=d["status"],
            is_starred=d["is_starred"],
            word_count=100,
        )
        session.add(item)
        items.append(item)
    session.commit()
    for item in items:
        session.refresh(item)
    return items


# ── List Tests ──

class TestListAnalyses:
    def test_list_all(
        self, client: TestClient, auth_headers: dict, multiple_analyses
    ):
        response = client.get("/api/reading", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4
        assert len(data["items"]) == 4

    def test_list_no_auth(self, client: TestClient):
        response = client.get("/api/reading")
        assert response.status_code == 401

    def test_filter_by_status(
        self, client: TestClient, auth_headers: dict, multiple_analyses
    ):
        response = client.get("/api/reading?status=new", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["status"] == "new"

    def test_filter_by_starred(
        self, client: TestClient, auth_headers: dict, multiple_analyses
    ):
        response = client.get("/api/reading?is_starred=true", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["is_starred"] is True

    def test_filter_by_min_quality(
        self, client: TestClient, auth_headers: dict, multiple_analyses
    ):
        response = client.get("/api/reading?min_quality=7", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["quality_score"] >= 7

    def test_pagination(
        self, client: TestClient, auth_headers: dict, multiple_analyses
    ):
        response = client.get("/api/reading?page=1&page_size=2", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 4
        assert data["page"] == 1

    def test_list_excludes_heavy_fields(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        """List endpoint should not include full content/analysis."""
        response = client.get("/api/reading", headers=auth_headers)
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert "content" not in item
        assert "analysis_html" not in item
        assert "analysis_json" not in item

    def test_shared_across_users(
        self, client: TestClient, admin_headers: dict, sample_analysis
    ):
        """Articles created by one user are visible to all authenticated users."""
        response = client.get("/api/reading", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["total"] == 1


# ── Get Detail Tests ──

class TestGetAnalysis:
    def test_get_detail(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        response = client.get(
            f"/api/reading/{sample_analysis.id}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "关于推进高质量发展的意见"
        assert data["content"] != ""
        assert data["analysis_html"] != ""
        assert isinstance(data["analysis_json"], dict)
        assert data["analysis_json"]["summary"] == "文章概述高质量发展的路径"
        assert len(data["analysis_json"]["highlights"]) == 1

    def test_get_nonexistent(self, client: TestClient, auth_headers: dict):
        response = client.get("/api/reading/9999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_accessible_by_other_user(
        self, client: TestClient, admin_headers: dict, sample_analysis
    ):
        """Any authenticated user can view any article detail."""
        response = client.get(
            f"/api/reading/{sample_analysis.id}", headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["title"] == "关于推进高质量发展的意见"


# ── Create Tests ──

class TestCreateAnalysis:
    @patch("httpx.AsyncClient")
    def test_create_success(
        self,
        mock_httpx_class,
        client: TestClient,
        auth_headers: dict,
        ai_config_db: AIConfig,
    ):
        """Test creating an analysis with mocked AI response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "quality_score": 8,
                        "quality_reason": "高质量时政文章",
                        "summary": "概述",
                        "highlights": [],
                        "overall_analysis": {"theme": "主题"},
                        "exam_points": {},
                        "vocabulary": [],
                        "reading_notes": "笔记",
                    })
                }
            }]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_class.return_value = mock_client_instance

        response = client.post(
            "/api/reading",
            headers=auth_headers,
            json={
                "title": "测试文章",
                "content": "这是测试内容" * 30,
                "source_url": "https://example.com",
                "source_name": "测试来源",
                "publish_date": "2024-06-01",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "测试文章"
        assert data["quality_score"] == 8

    def test_create_no_ai_config(
        self, client: TestClient, auth_headers: dict
    ):
        """Should fail if AI not configured."""
        response = client.post(
            "/api/reading",
            headers=auth_headers,
            json={"title": "测试", "content": "内容" * 20},
        )
        assert response.status_code == 400
        assert "配置AI" in response.json()["detail"]

    def test_create_no_auth(self, client: TestClient):
        response = client.post(
            "/api/reading",
            json={"title": "测试", "content": "内容"},
        )
        assert response.status_code == 401


# ── Update Status Tests ──

class TestUpdateStatus:
    def test_update_to_reading(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        response = client.put(
            f"/api/reading/{sample_analysis.id}/status",
            headers=auth_headers,
            json={"status": "reading"},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_update_to_finished(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        response = client.put(
            f"/api/reading/{sample_analysis.id}/status",
            headers=auth_headers,
            json={"status": "finished"},
        )
        assert response.status_code == 200

    def test_invalid_status(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        response = client.put(
            f"/api/reading/{sample_analysis.id}/status",
            headers=auth_headers,
            json={"status": "invalid"},
        )
        assert response.status_code == 400

    def test_update_nonexistent(self, client: TestClient, auth_headers: dict):
        response = client.put(
            "/api/reading/9999/status",
            headers=auth_headers,
            json={"status": "reading"},
        )
        assert response.status_code == 404


# ── Update Star Tests ──

class TestUpdateStar:
    def test_star(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        response = client.put(
            f"/api/reading/{sample_analysis.id}/star",
            headers=auth_headers,
            json={"is_starred": True},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    def test_unstar(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        response = client.put(
            f"/api/reading/{sample_analysis.id}/star",
            headers=auth_headers,
            json={"is_starred": False},
        )
        assert response.status_code == 200

    def test_star_nonexistent(self, client: TestClient, auth_headers: dict):
        response = client.put(
            "/api/reading/9999/star",
            headers=auth_headers,
            json={"is_starred": True},
        )
        assert response.status_code == 404


# ── Delete Tests ──

class TestDeleteAnalysis:
    def test_delete(
        self, client: TestClient, auth_headers: dict, sample_analysis
    ):
        response = client.delete(
            f"/api/reading/{sample_analysis.id}", headers=auth_headers
        )
        assert response.status_code == 204

        # Verify deleted
        response = client.get(
            f"/api/reading/{sample_analysis.id}", headers=auth_headers
        )
        assert response.status_code == 404

    def test_delete_nonexistent(self, client: TestClient, auth_headers: dict):
        response = client.delete("/api/reading/9999", headers=auth_headers)
        assert response.status_code == 404


# ── HTML Builder Tests ──

class TestHTMLBuilder:
    def test_build_analysis_html(self):
        from app.routers.article_analysis import _build_analysis_html

        data = {
            "summary": "测试概述",
            "overall_analysis": {
                "theme": "测试主题",
                "structure": "总分总",
                "core_arguments": ["论点1"],
            },
            "highlights": [
                {
                    "text": "重要句子",
                    "type": "key_point",
                    "color": "red",
                    "annotation": "这很重要",
                }
            ],
            "exam_points": {
                "essay_angles": ["角度1"],
                "golden_quotes": ["金句1"],
            },
            "vocabulary": [
                {"term": "术语1", "explanation": "解释1"}
            ],
            "reading_notes": "阅读笔记",
        }

        html = _build_analysis_html("测试标题", data)
        assert "测试概述" in html
        assert "测试主题" in html
        assert "重要句子" in html
        assert "角度1" in html
        assert "术语1" in html
        assert "阅读笔记" in html

    def test_build_html_empty_data(self):
        from app.routers.article_analysis import _build_analysis_html

        html = _build_analysis_html("空标题", {})
        assert html == ""

    def test_build_html_partial_data(self):
        from app.routers.article_analysis import _build_analysis_html

        html = _build_analysis_html("部分数据", {"summary": "只有概述"})
        assert "只有概述" in html
        assert "整体分析" not in html
