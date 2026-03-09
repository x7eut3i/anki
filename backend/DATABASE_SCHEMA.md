# Database Schema — 公考闪卡 Anki System

**Database:** SQLite (`backend/data/flashcards.db`)
**ORM:** SQLModel (SQLAlchemy + Pydantic)
**Last updated:** 2026-03

## Tables Overview

| # | Table | Description |
|---|---|---|
| 1 | `users` | 用户账号管理 |
| 2 | `categories` | 卡片分类 (常识判断/言语理解 等) |
| 3 | `decks` | 卡片牌组 |
| 4 | `cards` | 闪卡内容 |
| 5 | `user_card_progress` | 用户卡片学习进度 (FSRS) |
| 6 | `review_logs` | 复习记录日志 |
| 7 | `study_sessions` | 学习会话 |
| 8 | `ai_configs` | AI配置 (多配置支持) |
| 9 | `ai_usage_logs` | AI使用日志 (per-feature) |
| 10 | `ai_interaction_logs` | AI交互详细日志 (统计用) |
| 11 | `article_analyses` | 文章精读分析 |
| 12 | `article_sources` | 文章来源管理 |
| 13 | `ingestion_configs` | 自动抓取配置 |
| 14 | `ingestion_logs` | 抓取运行日志 |

---

## 1. `users`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| username | str(50) | UNIQUE, INDEX |
| email | str(255) | UNIQUE, INDEX |
| hashed_password | str | required |
| is_active | bool | default True |
| is_admin | bool | default False |
| created_at | datetime | default utcnow |
| updated_at | datetime | default utcnow |
| daily_new_limit | int | default 20 |
| daily_review_limit | int | default 200 |
| quiz_default_count | int | default 50 |
| target_retention | float | default 0.9 |
| session_max_minutes | int | default 30 |

---

## 2. `categories`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| name | str(50) | UNIQUE, INDEX |
| description | str(500) | default "" |
| icon | str(10) | default "📝" |
| sort_order | int | default 0 |
| is_active | bool | default True |
| created_at | datetime | default utcnow |
| exam_weight | int | default 10 |
| target_mastery | int | default 50 |

---

## 3. `decks`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| name | str(200) | INDEX |
| description | str(1000) | default "" |
| category_id | int | FK → categories.id, INDEX, nullable |
| is_default | bool | default False |
| sort_order | int | default 0 |
| created_at | datetime | default utcnow |
| updated_at | datetime | default utcnow |

---

## 4. `cards`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| deck_id | int | FK → decks.id, INDEX |
| category_id | int | FK → categories.id, INDEX, nullable |
| front | str(5000) | required |
| back | str(5000) | required |
| explanation | str(5000) | default "" |
| distractors | str | default "" (JSON array) |
| tags | str | default "" (comma-separated) |
| meta_info | str | default "" (JSON: knowledge, alternate_questions, exam_focus, pinyin 等) |
| source | str | default "" (来源URL) |
| expires_at | datetime | nullable (过期时间) |
| is_ai_generated | bool | default False |
| created_at | datetime | default utcnow |
| updated_at | datetime | default utcnow |

**Notes:** `distractors` non-empty → multiple-choice card; empty → Q&A card

---

## 5. `user_card_progress`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| user_id | int | FK → users.id, INDEX |
| card_id | int | FK → cards.id, INDEX |
| due | datetime | INDEX, default utcnow |
| stability | float | default 0.0 |
| difficulty | float | default 0.0 |
| elapsed_days | int | default 0 |
| scheduled_days | int | default 0 |
| reps | int | default 0 |
| state | int | default 0 (CardState enum) |
| last_review | datetime | nullable |
| is_suspended | bool | default False |
| created_at | datetime | default utcnow |
| updated_at | datetime | default utcnow |

**Unique constraint:** (user_id, card_id)

**CardState enum:** 0=New, 1=Learning, 2=Review, 3=Relearning

---

## 6. `review_logs`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| card_id | int | FK → cards.id, INDEX |
| user_id | int | FK → users.id, INDEX |
| rating | int | required (1=Again, 2=Hard, 3=Good, 4=Easy) |
| state | int | required (CardState before review) |
| due | datetime | required (due date before review) |
| stability | float | required |
| difficulty | float | required |
| elapsed_days | int | required |
| scheduled_days | int | required |
| review_duration_ms | int | default 0 |
| reviewed_at | datetime | default utcnow |

---

## 7. `study_sessions`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| user_id | int | FK → users.id, INDEX |
| mode | str | default "review" (review/mix/quiz) |
| deck_ids | str | default "" (comma-separated) |
| category_id | int | FK → categories.id, nullable |
| total_cards | int | default 0 |
| cards_reviewed | int | default 0 |
| correct_count | int | default 0 |
| wrong_count | int | default 0 |
| new_cards_studied | int | default 0 |
| time_limit_minutes | int | default 0 |
| started_at | datetime | default utcnow |
| finished_at | datetime | nullable |
| is_completed | bool | default False |
| card_order | str | default "[]" (JSON) |
| session_data | str | default "{}" (JSON) |

---

## 8. `ai_configs`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| user_id | int | FK → users.id, INDEX |
| name | str | default "默认" |
| is_active | bool | default True |
| api_base_url | str | default "https://api.openai.com/v1" |
| api_key | str | default "" |
| model | str | default "gpt-4o-mini" |
| model_pipeline | str | default "" (文章管线卡片生成模型) |
| model_reading | str | default "" (精读分析模型) |
| max_daily_calls | int | default 50 |
| import_batch_size | int | default 30 |
| max_tokens | int | default 8192 |
| temperature | float | default 0.3 |
| is_enabled | bool | default False |
| auto_explain_wrong | bool | default True |
| auto_generate_mnemonics | bool | default False |
| auto_generate_related | bool | default False |
| updated_at | datetime | default utcnow |

---

## 9. `ai_usage_logs`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| user_id | int | FK → users.id, INDEX |
| feature | str | required |
| tokens_used | int | default 0 |
| cost_usd | float | default 0.0 |
| created_at | datetime | default utcnow |

**Feature values:** explain, mnemonic, generate, ingest, chat, complete, smart_import, batch_enrich

---

## 10. `ai_interaction_logs` *(NEW)*

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| user_id | int | INDEX, nullable |
| feature | str | INDEX (article_analysis / card_generation / ingestion_analysis / content_cleanup / etc.) |
| model | str | default "" |
| config_name | str | default "" |
| tokens_used | int | default 0 |
| elapsed_ms | int | default 0 |
| status | str | default "ok" (ok / error) |
| error_message | str | default "" |
| input_preview | str | default "" (~200 chars of prompt) |
| output_length | int | default 0 |
| created_at | datetime | default utcnow |

**Purpose:** Replaces unreliable file-based AI log parsing for statistics. Powers `/api/stats/ai` endpoint.

---

## 11. `article_analyses`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| user_id | int | FK → users.id, INDEX |
| title | str(500) | required |
| source_url | str(2000) | default "" |
| source_name | str(100) | default "" |
| publish_date | str(20) | default "" |
| content | text | default "" |
| analysis_json | text | default "" |
| analysis_html | text | default "" |
| quality_score | int | default 0 (1-10) |
| reading_notes | text | default "" |
| cards_created | int | default 0 |
| status | str | default "new" (new/reading/finished/archived) |
| is_starred | bool | default False |
| created_at | datetime | default utcnow |
| updated_at | datetime | default utcnow |
| deleted_at | datetime | nullable |
| last_read_at | datetime | nullable, auto-updated on read |

---

## 12. `article_sources`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| name | str(200) | required |
| url | str(2000) | required |
| source_type | str | default "html" (rss/html) |
| category | str | default "时政热点" |
| is_active | bool | default True |
| is_default | bool | default False |
| description | str | default "" |
| last_fetched | datetime | nullable |
| created_at | datetime | default utcnow |

---

## 13. `ingestion_configs`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| is_enabled | bool | default False |
| schedule_hour | int | default 6 |
| schedule_minute | int | default 0 |
| schedule_type | str | default "daily" |
| schedule_days | str | default "" |
| cron_expression | str | default "" |
| timezone | str | default "Asia/Shanghai" |
| quality_threshold | int | default 7 |
| auto_analyze | bool | default True |
| auto_create_cards | bool | default True |
| updated_at | datetime | default utcnow |

---

## 14. `ingestion_logs`

| Column | Type | Constraints |
|---|---|---|
| id | int | PK, auto |
| trigger_type | str | default "manual" (manual/scheduled) |
| status | str | default "running" (running/success/error) |
| started_at | datetime | default utcnow |
| finished_at | datetime | nullable |
| sources_checked | int | default 0 |
| articles_fetched | int | default 0 |
| articles_analyzed | int | default 0 |
| cards_created | int | default 0 |
| errors_count | int | default 0 |
| total_tokens | int | default 0 |
| log_detail | str | default "" (JSON array) |

---

## Relationship Diagram

```
users ──────┬──< ai_configs
            ├──< ai_usage_logs
            ├──< study_sessions ──> decks, categories
            ├──< review_logs ──> cards
            ├──< user_card_progress ──> cards
            └──< article_analyses

categories ──< decks
categories ──< cards

decks ──< cards

cards ──< user_card_progress (UQ: user_id + card_id)
cards ──< review_logs

article_sources (standalone)
ingestion_configs (standalone)
ingestion_logs (standalone)
ai_interaction_logs (standalone, user_id not FK)
```

## API Endpoints Using These Tables

| Table | Primary Router | Key Endpoints |
|---|---|---|
| users | `/api/auth`, `/api/users` | Login, register, user management |
| categories | `/api/categories` | List/CRUD categories |
| decks | `/api/decks` | List/CRUD decks |
| cards | `/api/cards` | List/CRUD/bulk cards |
| user_card_progress | `/api/review` | FSRS scheduling |
| review_logs | `/api/review`, `/api/stats/study` | Review answers, study stats |
| study_sessions | `/api/review` | Session management |
| ai_configs | `/api/ai` | AI configuration |
| ai_usage_logs | `/api/ai` | Usage tracking |
| ai_interaction_logs | `/api/stats/ai` | AI statistics |
| article_analyses | `/api/reading` | Article analysis & reading |
| article_sources | `/api/sources` | Source management |
| ingestion_configs | `/api/ingestion` | Auto-fetch config |
| ingestion_logs | `/api/ingestion`, `/api/stats/content` | Run logs, content stats |
