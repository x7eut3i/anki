# 更新日志 (Changelog)

## v1.1.0 — 功能增强版

**发布日期：** 2025-01

---

### 🏷️ 自定义标签系统

全新的标签管理功能，支持为卡片和文章添加自定义分类标签。

**后端变更：**
- 新增 3 张数据库表：`tags`（标签）、`card_tags`（卡片-标签关联）、`article_tags`（文章-标签关联）
- 新增标签管理 API 路由 `/api/tags`：
  - `GET /api/tags` — 列出所有标签（含使用计数）
  - `POST /api/tags` — 创建标签（名称+颜色）
  - `PUT /api/tags/{id}` — 编辑标签
  - `DELETE /api/tags/{id}` — 删除标签（自动清理关联关系）
  - `GET /api/tags/card/{card_id}` — 查询卡片标签
  - `POST /api/tags/card/{card_id}/add/{tag_id}` — 为卡片添加标签
  - `DELETE /api/tags/card/{card_id}/remove/{tag_id}` — 移除卡片标签
  - `GET /api/tags/article/{article_id}` — 查询文章标签
  - `POST /api/tags/article/{article_id}/add/{tag_id}` — 为文章添加标签
  - `DELETE /api/tags/article/{article_id}/remove/{tag_id}` — 移除文章标签
- 新建文件：`backend/app/models/tag.py`、`backend/app/routers/tags.py`

**前端变更：**
- 新增「标签管理」页面（`/tags`），支持：
  - 创建、编辑、删除标签
  - 10 种预设颜色选择
  - 实时预览标签样式
  - 显示每个标签关联的卡片数和文章数
- 侧边栏「卡片管理」分组新增「标签管理」入口
- 前端 API 客户端新增 `tags` 模块

---

### 🔄 AI 异步任务系统

支持将耗时 AI 操作放入后台执行，前端可查询任务进度。

**后端变更：**
- 新增 `ai_jobs` 数据库表，跟踪异步任务状态（pending → running → completed/failed）
- 新增任务管理 API `/api/jobs`：
  - `GET /api/jobs` — 列出当前用户的任务
  - `GET /api/jobs/{id}` — 查询任务详情
  - `DELETE /api/jobs/{id}` — 删除已完成/失败的任务
  - `DELETE /api/jobs` — 清理所有已完成/失败的任务
- 新增异步版 AI 端点：
  - `POST /api/ai/smart-import/async` — 后台智能导入
  - `POST /api/ai/batch-enrich/async` — 后台批量补充
- 新建文件：`backend/app/models/ai_job.py`、`backend/app/routers/ai_jobs.py`
- 提供 `create_job()` 和 `update_job_status()` 工具函数供其他路由复用

**前端变更：**
- 前端 API 客户端新增 `jobs` 模块和异步 AI 端点

---

### ⚙️ AI 重试机制可配置

AI 调用失败时的重试逻辑现在完全可配置。

**后端变更：**
- `AIConfig` 模型新增 `max_retries` 字段（默认 3 次）
- `AIService.chat_completion()` 方法改为循环重试 + 指数退避
  - 间隔公式：`2 × (attempt + 1)` 秒
  - 超时从 60s 增至 120s
- 文章精读分析的重试逻辑也改用 `config.max_retries`（之前硬编码为 2 次）
- `AIConfigResponse`/`AIConfigUpdate`/`AIConfigCreate` schema 均新增 `max_retries` 字段

**前端变更：**
- AI 助手配置页面新增「AI 重试次数」输入框
- 支持 1-10 次重试配置，附带使用说明

---

### 📚 文章精读增强

**文章导入/导出：**
- 新增 `GET /api/reading/export/articles` — 导出所有文章为 JSON
- 新增 `POST /api/reading/import/articles` — 导入文章 JSON（按 `source_url` + `title` 去重）
- 文章精读列表页顶部新增「📥 导出文章」和「📤 导入文章」按钮

**重新分析按钮：**
- 文章详情页的「重新分析」按钮现在**始终显示**，不再仅在分析失败时显示
- 对已有分析结果的文章，点击时会弹出确认对话框
- 无分析结果的文章使用醒目的橙色按钮

**关联卡片管理：**
- 新增 `GET /api/reading/{id}/cards` — 获取文章关联的卡片列表
- 新增 `DELETE /api/reading/{id}/cards/{card_id}` — 删除指定关联卡片
- 文章详情页的「本文关联卡片」区域，每张卡片右侧新增红色删除按钮
- 删除时弹出确认提示，删除后实时更新列表

---

### 📝 模拟测试题型修正

修正了模拟测试和复习模式的题型比例。

**变更：**
- **模拟测试（quiz 模式）**：100% 选择题
  - 前端现在明确传递 `include_types: ["choice"]`
- **复习/混合模式**：60% 问答题 + 40% 选择题
  - `quiz_service._card_to_question()` 根据 `include_types` 参数动态调整比例
  - 当 `include_types` 包含 `"qa"` 时，60% 概率生成问答题
  - 当 `include_types` 仅包含 `"choice"` 时，100% 选择题

---

### 🧹 废弃功能清理

**移除「智能导入 - 系统提示词（已弃用）」：**
- 从 `prompts.py` 的 `_get_default_prompts()` 中移除 `smart_import` 条目
- 前端 Prompt 管理页面过滤掉 `prompt_key === "smart_import"` 的项
- 智能导入功能仍然可用，统一使用「卡片生成」系统提示词

**移除侧边栏「学习」标签页：**
- 从侧边栏「学习」分组中移除 `{ href: "/study", label: "学习" }` 导航项
- 学习功能通过仪表盘和模拟测试页面访问

---

### 🔍 牌组管理搜索优化

**搜索体验改进：**
- 移除了防抖（debounce）即时搜索，改为手动触发
- 新增「搜索」按钮，也支持按 Enter 键触发
- 搜索结果以**卡片列表**形式展示（非牌组卡片形式），包含：
  - 卡片正面/背面预览
  - 标签 Badge 显示
  - 「查看牌组 →」快速跳转链接
- 新增「×」按钮清除搜索结果

**标签筛选：**
- 新增标签下拉筛选器（当有自定义标签时显示）
- 与分类筛选器并列使用

---

### 📁 修改的文件清单

#### 新增文件
| 文件 | 说明 |
|------|------|
| `backend/app/models/tag.py` | Tag、CardTag、ArticleTag 数据模型 |
| `backend/app/models/ai_job.py` | AIJob 异步任务数据模型 |
| `backend/app/routers/tags.py` | 标签管理 API（完整 CRUD + 关联操作） |
| `backend/app/routers/ai_jobs.py` | 异步任务管理 API + 工具函数 |
| `frontend/src/app/(app)/tags/page.tsx` | 标签管理页面 |

#### 修改文件
| 文件 | 变更内容 |
|------|----------|
| `backend/app/main.py` | 注册 tags、ai_jobs 两个新路由 |
| `backend/app/models/__init__.py` | 导出 Tag、CardTag、ArticleTag、AIJob |
| `backend/app/models/ai_config.py` | 新增 `max_retries` 字段 |
| `backend/app/schemas/ai.py` | AIConfigUpdate/Response/Create 新增 `max_retries` |
| `backend/app/services/ai_service.py` | chat_completion 改为可配置重试+指数退避 |
| `backend/app/services/quiz_service.py` | _card_to_question 按 include_types 调整题型比例 |
| `backend/app/routers/ai.py` | 导入异步工具，新增 /smart-import/async 和 /batch-enrich/async，max_retries 写入响应 |
| `backend/app/routers/article_analysis.py` | 重试用 config.max_retries，新增文章导入/导出/卡片管理端点 |
| `backend/app/routers/prompts.py` | 移除 smart_import 默认提示词 |
| `frontend/src/components/sidebar.tsx` | 移除「学习」导航项，新增「标签管理」 |
| `frontend/src/lib/api.ts` | 新增 tags、jobs API 模块，reading 新增 export/import/cards 方法 |
| `frontend/src/app/(app)/quiz/page.tsx` | 传递 `include_types: ["choice"]` |
| `frontend/src/app/(app)/decks/page.tsx` | 搜索改为手动触发+卡片列表结果+标签筛选 |
| `frontend/src/app/(app)/reading/page.tsx` | 重新分析按钮始终显示，关联卡片可删除，新增导入/导出按钮 |
| `frontend/src/app/(app)/prompt-config/page.tsx` | 过滤已弃用的 smart_import 提示词 |
| `frontend/src/app/(app)/ai/page.tsx` | 新增 max_retries 配置项 UI |

---

### 🗄️ 数据库迁移

本次更新新增以下数据表（SQLModel 自动创建）：

```sql
-- 标签表
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    color VARCHAR(20) DEFAULT '#3b82f6',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 卡片-标签关联表
CREATE TABLE card_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    UNIQUE(card_id, tag_id)
);

-- 文章-标签关联表
CREATE TABLE article_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES article_analyses(id),
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    UNIQUE(article_id, tag_id)
);

-- AI 异步任务表
CREATE TABLE ai_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    job_type VARCHAR(50) NOT NULL,
    title VARCHAR(500) DEFAULT '',
    status VARCHAR(20) DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    result_json TEXT DEFAULT '',
    error_message VARCHAR(2000) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

> **注意：** `ai_configs` 表新增 `max_retries INTEGER DEFAULT 3` 列。SQLModel 会自动处理新列添加。
