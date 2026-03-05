# 数据库表结构 (Database Schema)

本文档描述了 Anki 公务员考试刷题应用的所有数据库表结构。

数据库：SQLite (通过 SQLModel/SQLAlchemy ORM 管理)

## 架构说明

- **Cards 和 Decks 是共享的**：不再按用户隔离，所有用户看到相同的牌组和卡片内容
- **FSRS 调度数据按用户隔离**：通过 `user_card_progress` 表，每个用户独立跟踪学习进度
- **卡片类型动态判断**：通过 `distractors` 字段是否为空判断题型（选择题/问答题）

---

## 1. `users` — 用户表

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 用户ID |
| username | VARCHAR(50) | UNIQUE, INDEX | - | 用户名 |
| email | VARCHAR(255) | UNIQUE, INDEX | - | 邮箱 |
| hashed_password | TEXT | NOT NULL | - | 密码哈希 (bcrypt) |
| is_active | BOOLEAN | | True | 是否激活 |
| is_admin | BOOLEAN | | False | 是否管理员 |
| created_at | DATETIME | | now(utc) | 创建时间 |
| updated_at | DATETIME | | now(utc) | 更新时间 |
| daily_new_card_limit | INTEGER | | 20 | 每日新卡数量限制 |
| daily_review_limit | INTEGER | | 200 | 每日复习数量限制 |
| session_card_limit | INTEGER | | 50 | 单次学习卡片数量限制 |
| desired_retention | FLOAT | | 0.9 | 期望记忆保留率 |
| ai_import_batch_size | INTEGER | | 30 | AI导入批次大小 |

---

## 2. `categories` — 分类表

应用预设20个默认分类（成语、实词辨析、法律常识等），在首次启动时自动种入。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 分类ID |
| name | VARCHAR(50) | UNIQUE, INDEX | - | 分类名称 |
| description | VARCHAR(500) | | "" | 分类描述 |
| icon | VARCHAR(10) | | "📝" | 分类图标 (emoji) |
| sort_order | INTEGER | | 0 | 排序顺序 |
| is_active | BOOLEAN | | True | 是否启用 |
| created_at | DATETIME | | now(utc) | 创建时间 |
| default_new_per_day | INTEGER | | 10 | 默认每日新卡数 |
| default_reviews_per_day | INTEGER | | 50 | 默认每日复习数 |

**预设分类列表：**
成语、实词辨析、规范词、时政热点、法律常识、政治理论、历史文化、地理科技、经济常识、常识判断、逻辑推理、数量关系、资料分析、申论素材、古诗词名句、公文写作、马克思主义哲学、习近平重要论述、党史、易错题集

---

## 3. `decks` — 牌组表（共享）

> **注意**：牌组不再有 `user_id` 字段，所有用户共享同一套牌组。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 牌组ID |
| name | VARCHAR(200) | INDEX | - | 牌组名称 |
| description | VARCHAR(1000) | | "" | 牌组描述 |
| category_id | INTEGER | FK→categories.id, INDEX | NULL | 所属分类 |
| is_public | BOOLEAN | | False | 是否公开 |
| card_count | INTEGER | | 0 | 卡片计数（冗余字段，便于展示） |
| created_at | DATETIME | | now(utc) | 创建时间 |
| updated_at | DATETIME | | now(utc) | 更新时间 |

---

## 4. `cards` — 卡片表（共享，仅存内容）

> **注意**：卡片不再有 `user_id` 和 FSRS 调度字段。FSRS 数据存储在 `user_card_progress` 表中。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 卡片ID |
| deck_id | INTEGER | FK→decks.id, INDEX | - | 所属牌组 |
| category_id | INTEGER | FK→categories.id, INDEX | NULL | 所属分类 |
| **内容字段** | | | | |
| front | VARCHAR(5000) | | - | 问题/题干 |
| back | VARCHAR(5000) | | - | 答案（始终为正确答案文本） |
| explanation | VARCHAR(5000) | | "" | 详细解析 |
| distractors | TEXT | | "" | JSON数组，3个干扰项（错误答案）。非空时为选择题，空时为问答题 |
| tags | TEXT | | "" | 逗号分隔标签 |
| meta_info | TEXT | | "" | JSON结构化知识信息（见下方schema） |
| source | TEXT | | "" | 来源URL |
| source_date | TEXT | | "" | 来源日期 |
| expires_at | DATETIME | | NULL | 过期时间（时政热点自动退休） |
| **元数据** | | | | |
| is_ai_generated | BOOLEAN | | False | 是否AI生成 |
| ai_review_status | VARCHAR | | "approved" | AI审核状态：pending/approved/rejected |
| created_at | DATETIME | | now(utc) | 创建时间 |
| updated_at | DATETIME | | now(utc) | 更新时间 |

### 题型说明

卡片不存储题型字段，而是通过 `distractors` 动态判断：
- **选择题（choice）**：`distractors` 非空（包含3个错误答案），`back` 为正确答案文本
- **问答题（Q&A）**：`distractors` 为空，`back` 为答案文本

问答题包含多种变体：成语释义、规范词、名句补全、概念填空等。

### `meta_info` JSON Schema

`meta_info` 字段存储结构化的知识信息，用于动态出题、近义词/反义词提示、考点标注等。

```json
{
  "knowledge_type": "idiom|law|politics|economics|history|general",
  "subject": "核心知识点主题（简短描述）",
  "pinyin": "拼音标注（成语卡片专用，如 zhāng guān lǐ dài）",
  "knowledge": {
    "synonyms": ["近义词/同义表述"],
    "antonyms": ["反义词/对立概念"],
    "related": ["相关知识点"],
    "key_points": ["核心考点1", "核心考点2"],
    "golden_quotes": ["可引用的金句"],
    "formal_terms": ["规范表述/公文用语"],
    "essay_material": "申论可用素材概述",
    "memory_tips": "记忆技巧/口诀"
  },
  "exam_focus": {
    "xingce_relevant": true,
    "shenlun_relevant": false,
    "difficulty": "easy|medium|hard",
    "frequency": "high|medium|low"
  },
  "alternate_questions": [
    {"type": "choice", "question": "变体选择题", "answer": "正确答案", "choices": ["选项A", "选项B", "选项C", "选项D"]},
    {"type": "qa", "question": "变体问答题", "answer": "答案"}
  ],
  "facts": {"关键事实名": "事实值"}
}
```

**兼容性说明：**
- **手动上传的卡片**：`meta_info` 可以为空字符串 `""`，只需要 `front` + `back`
- **AI生成的卡片**：`meta_info` 完整填充，包含 `knowledge`、`exam_focus` 等
- **导入的卡片**：可以只有部分字段，缺失字段使用空值

---

## 5. `user_card_progress` — 用户卡片学习进度表（按用户隔离）

> **核心表**：存储每个用户对每张卡片的 FSRS 调度数据和学习状态。卡片内容共享，但学习进度按用户独立跟踪。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 进度ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 用户ID |
| card_id | INTEGER | FK→cards.id, INDEX | - | 卡片ID |
| due | DATETIME | INDEX | now(utc) | 下次复习时间 |
| stability | FLOAT | | 0.0 | FSRS稳定性 |
| difficulty | FLOAT | | 0.0 | FSRS难度 |
| step | INTEGER | | 0 | 学习步骤 |
| reps | INTEGER | | 0 | 重复次数 |
| lapses | INTEGER | | 0 | 遗忘次数 |
| state | INTEGER | | 0 | 状态：0=New, 1=Learning, 2=Review, 3=Relearning |
| last_review | DATETIME | | NULL | 上次复习时间 |
| is_suspended | BOOLEAN | | False | 是否暂停 |
| created_at | DATETIME | | now(utc) | 创建时间 |
| updated_at | DATETIME | | now(utc) | 更新时间 |

**唯一约束：** `(user_id, card_id)` — 每个用户对每张卡片最多一条记录

---

## 6. `review_logs` — 复习日志表

记录每次卡片复习的详细数据，用于FSRS算法分析。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 日志ID |
| card_id | INTEGER | FK→cards.id, INDEX | - | 卡片ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 用户ID |
| rating | INTEGER | | - | 评分：1=Again, 2=Hard, 3=Good, 4=Easy |
| state | INTEGER | | - | 复习前的卡片状态 |
| due | DATETIME | | - | 复习前的到期时间 |
| stability | FLOAT | | - | 复习前的稳定性 |
| difficulty | FLOAT | | - | 复习前的难度 |
| elapsed_days | INTEGER | | - | 距上次复习天数 |
| scheduled_days | INTEGER | | - | 计划间隔天数 |
| review_duration_ms | INTEGER | | 0 | 作答时长（毫秒） |
| reviewed_at | DATETIME | | now(utc) | 复习时间 |

---

## 7. `study_sessions` — 学习会话表

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 会话ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 用户ID |
| mode | VARCHAR | | "review" | 模式：review/mix/quiz |
| category_ids | TEXT | | "" | 逗号分隔分类ID（mix模式） |
| deck_id | INTEGER | FK→decks.id | NULL | 牌组ID |
| total_cards | INTEGER | | 0 | 总卡片数 |
| cards_reviewed | INTEGER | | 0 | 已复习数 |
| cards_correct | INTEGER | | 0 | 正确数 |
| cards_again | INTEGER | | 0 | 重来数 |
| quiz_score | INTEGER | | 0 | 测验分数 |
| quiz_time_limit | INTEGER | | 0 | 时间限制（秒），0=无限 |
| started_at | DATETIME | | now(utc) | 开始时间 |
| finished_at | DATETIME | | NULL | 结束时间 |
| is_completed | BOOLEAN | | False | 是否完成 |
| remaining_card_ids | TEXT | | "[]" | 剩余卡片ID列表 (JSON) |
| quiz_answer_map | TEXT | | "{}" | 动态题目答案映射 (JSON) |

---

## 8. `ai_configs` — AI配置表

每个用户独立的AI服务配置。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 配置ID |
| user_id | INTEGER | FK→users.id, UNIQUE, INDEX | - | 用户ID（一对一） |
| api_base_url | VARCHAR | | "https://api.openai.com/v1" | API端点 |
| api_key | VARCHAR | | "" | API密钥 |
| model | VARCHAR | | "gpt-4o-mini" | 默认模型名称 |
| model_pipeline | VARCHAR | | "" | 文章管道/卡片生成专用模型（空=使用默认） |
| model_reading | VARCHAR | | "" | 文章精读分析专用模型（空=使用默认） |
| max_daily_calls | INTEGER | | 50 | 每日调用限制 |
| is_enabled | BOOLEAN | | False | 是否启用 |
| auto_explain_wrong | BOOLEAN | | True | 自动解释错题 |
| auto_generate_mnemonics | BOOLEAN | | False | 自动生成记忆口诀 |
| auto_generate_related | BOOLEAN | | False | 自动生成相关题目 |
| updated_at | DATETIME | | now(utc) | 更新时间 |

---

## 9. `ai_usage_logs` — AI使用日志表

跟踪AI API调用次数和token消耗。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 日志ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 用户ID |
| feature | VARCHAR | | - | 功能：explain/mnemonic/generate/ingest/chat |
| tokens_used | INTEGER | | 0 | Token消耗 |
| cost_estimate | FLOAT | | 0.0 | 预估费用 |
| created_at | DATETIME | | now(utc) | 调用时间 |

---

## 10. `article_analyses` — 文章精读表

AI驱动的时政文章深度阅读分析。由文章管道自动生成或用户手动创建。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 分析ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 创建者用户ID |
| title | VARCHAR(500) | NOT NULL | - | 文章标题 |
| source_url | VARCHAR(2000) | | "" | 文章来源URL |
| source_name | VARCHAR(100) | | "" | 来源名称（如：人民日报评论） |
| publish_date | VARCHAR(20) | | "" | 发布日期 (YYYY-MM-DD) |
| content | TEXT | | "" | 文章原文全文 |
| analysis_html | TEXT | | "" | AI生成的富文本HTML（含标注、配色） |
| analysis_json | TEXT | | "" | 结构化分析JSON（highlights/exam_points等） |
| quality_score | INTEGER | | 0 | 文章质量评分 (1-10)，AI评估 |
| quality_reason | TEXT | | "" | 评分理由 |
| word_count | INTEGER | | 0 | 文章字数 |
| status | VARCHAR | | "new" | 阅读状态：new/reading/finished |
| is_starred | BOOLEAN | | False | 是否收藏 |
| created_at | DATETIME | | now(utc) | 创建时间 |
| updated_at | DATETIME | | now(utc) | 更新时间 |
| finished_at | DATETIME | | NULL | 完成阅读时间 |

**`analysis_json` 结构说明：**

```json
{
  "quality_score": 8,
  "quality_reason": "评分理由",
  "summary": "文章概述 (100-200字)",
  "overall_analysis": {
    "theme": "主题",
    "structure": "结构分析",
    "writing_style": "写作特点",
    "core_arguments": ["论点1", "论点2"],
    "logical_chain": "论证逻辑"
  },
  "highlights": [
    {
      "text": "原文句段",
      "type": "key_point|policy|data|quote|terminology|exam_focus",
      "color": "red|orange|blue|green|purple",
      "annotation": "批注解析"
    }
  ],
  "exam_points": {
    "essay_angles": ["申论角度"],
    "formal_terms": ["规范表述"],
    "golden_quotes": ["金句"],
    "background_knowledge": ["背景知识"],
    "possible_questions": ["可能考法"]
  },
  "vocabulary": [
    { "term": "术语", "explanation": "释义" }
  ],
  "reading_notes": "阅读建议和笔记"
}
```

---

## 11. `article_sources` — 文章来源表

可管理的文章抓取来源列表。用户可通过界面添加/禁用来源。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 来源ID |
| name | VARCHAR(200) | NOT NULL | - | 来源名称（如"人民日报-时政"） |
| url | VARCHAR(2000) | NOT NULL | - | 来源URL |
| source_type | VARCHAR(20) | | "rss" | 类型：rss/html |
| category | VARCHAR(50) | | "时政热点" | 文章分类标签 |
| is_enabled | BOOLEAN | | True | 是否启用 |
| description | TEXT | | "" | 来源描述 |
| last_fetched_at | DATETIME | | NULL | 上次抓取时间 |
| created_at | DATETIME | | now(utc) | 创建时间 |

---

## 12. `prompt_configs` — 提示词配置表

可编辑的AI提示词模板，用于自定义各功能的AI行为。

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 配置ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 用户ID |
| prompt_key | VARCHAR(100) | INDEX | - | 提示词标识（card_system/article_analysis/batch_enrich/smart_import/card_from_selection） |
| system_prompt | TEXT | | "" | 系统提示词内容 |
| model | VARCHAR(100) | | "" | 专用模型（空=使用默认） |
| is_active | BOOLEAN | | True | 是否启用 |
| updated_at | DATETIME | | now(utc) | 更新时间 |

**唯一约束：** `(user_id, prompt_key)` — 每个用户的每个提示词标识最多一条

**prompt_key 取值说明：**
- `card_system` — 卡片生成系统提示词
- `article_analysis` — 文章精读分析提示词
- `batch_enrich` — 批量补充卡片提示词
- `smart_import` — AI智能导入提示词
- `card_from_selection` — 选文生成卡片提示词

---

## 13. `ingestion_configs` — 自动抓取配置表

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 配置ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 用户ID |
| is_enabled | BOOLEAN | | False | 是否启用自动抓取 |
| schedule_hour | INTEGER | | 6 | 每日抓取时间（小时） |
| schedule_minute | INTEGER | | 0 | 每日抓取时间（分钟） |
| cron_expression | TEXT | | "" | Cron表达式（优先级高于schedule_hour/minute） |
| concurrency | INTEGER | | 1 | 并发抓取数（1-5） |
| max_articles_per_source | INTEGER | | 5 | 每来源最大文章数 |
| quality_threshold | INTEGER | | 6 | 质量评分阈值（低于此分不生成卡片） |
| auto_analyze | BOOLEAN | | True | 自动进行精读分析 |
| auto_create_cards | BOOLEAN | | True | 自动生成卡片 |
| target_deck_id | INTEGER | FK→decks.id | NULL | 目标牌组ID |
| created_at | DATETIME | | now(utc) | 创建时间 |
| updated_at | DATETIME | | now(utc) | 更新时间 |

---

## 14. `ingestion_logs` — 抓取日志表

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, AUTO | - | 日志ID |
| user_id | INTEGER | FK→users.id, INDEX | - | 用户ID |
| run_type | VARCHAR(20) | | "manual" | 触发类型：manual/auto |
| status | VARCHAR(20) | | "running" | 状态：running/completed/failed |
| sources_count | INTEGER | | 0 | 来源数 |
| articles_fetched | INTEGER | | 0 | 抓取文章数 |
| articles_analyzed | INTEGER | | 0 | 分析文章数 |
| cards_created | INTEGER | | 0 | 生成卡片数 |
| error_message | TEXT | | "" | 错误信息 |
| details | TEXT | | "[]" | 详细日志（JSON数组） |
| started_at | DATETIME | | now(utc) | 开始时间 |
| finished_at | DATETIME | | NULL | 结束时间 |

---

## 表关系图 (ER Diagram)

```
users ─────────┬─── user_card_progress ─── cards ─── decks
    │          │                                │
    │          ├─── review_logs ────────────────┘
    │          │
    │          ├─── study_sessions ─── decks
    │          │
    │          ├─── ai_configs (1:N)
    │          │
    │          ├─── ai_usage_logs
    │          │
    │          ├─── article_analyses
    │          │
    │          ├─── prompt_configs
    │          │
    │          ├─── ingestion_configs
    │          │
    │          └─── ingestion_logs
    │
categories ────┬─── decks
               └─── cards

article_sources (独立表, 无FK)
```

### 关系说明：
- `users` 1:N `user_card_progress` — 用户学习进度
- `users` 1:N `review_logs` — 复习日志
- `users` 1:N `study_sessions` — 学习会话
- `users` 1:N `ai_configs` — AI配置（支持多配置）
- `users` 1:N `ai_usage_logs` — AI使用日志
- `users` 1:N `article_analyses` — 文章精读分析
- `users` 1:N `prompt_configs` — 提示词配置
- `users` 1:N `ingestion_configs` — 抓取配置
- `users` 1:N `ingestion_logs` — 抓取日志
- `cards` 1:N `user_card_progress` — 每张卡片可有多个用户的进度
- `cards` 1:N `review_logs` — 复习日志
- `decks` 1:N `cards` — 牌组包含卡片
- `categories` 1:N `decks`, `cards` — 分类关联
