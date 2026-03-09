# Anki Flashcard App

公务员考试智能刷题系统 — 基于 **FSRS-6** 间隔重复算法的全功能学习平台。支持 AI 出题、文章精读、自动抓取时政热点、多模式练习、PWA 离线使用。

## 功能总览

### 📚 核心学习

- **FSRS-6 间隔重复** — 业界领先的记忆调度算法，根据每张卡片的难度和你的记忆曲线自动安排复习时间，实现最优记忆保留率
- **多题型支持** — 问答题、四选一选择题、填空题、判断题、完形填空，同一卡片可在问答与选择之间动态切换
- **20 个预设分类** — 成语、实词辨析、规范词、时政热点、法律常识、政治理论、历史文化、地理科技、经济常识、常识判断、逻辑推理、数量关系、资料分析、申论素材、古诗词名句、公文写作、马克思主义哲学、习近平重要论述、党史、易错题集
- **出题比例自定义** — 每次学习前可选「全问答」「全选择」或自定义比例（如 60% 问答 + 40% 选择），设置自动保存到账户
- **离线答题** — 学习/练习/测试时所有卡片、预览数据、标签、文章信息等资源一次性预加载到本地，答题过程零网络请求，仅在完成或手动「暂存进度」时批量提交答案

### 🧠 学习模式

- **复习模式** — 按 FSRS 算法推荐到期卡片，逐张评分（Again/Hard/Good/Easy），算法根据评分调整下次复习时间
- **混合模式** — 跨分类交叉练习，打乱知识域防止思维固化，支持多分类/多牌组/多标签组合
- **模拟测试** — 定时限时考试，按分类/牌组选题，自动评分，显示正确率和逐题解析。支持暂存和会话恢复
- **会话恢复** — 学习/混合练习中途退出后可从断点继续，保留已答题记录和进度；模拟测试会话通过 localStorage 持久化，可从 Dashboard 一键恢复

### 🤖 AI 智能功能

- **AI 出题** — 粘贴任意文本，AI 自动生成高质量闪卡（含干扰项、解析、元数据），支持 OpenAI 兼容 API
- **AI 智能导入** — 上传 CSV/JSON/Excel/TXT 等任意格式文件，AI 自动识别结构并转换为标准卡片，支持批量处理和自动分类。使用 `_ai_call_with_retry` 统一重试机制，支持 RPM 限速、Fallback 模型自动切换、配额检测
- **AI 精读分析** — 上传或抓取文章后，AI 生成结构化分析：核心观点、政策要点、数据支撑、金句标注、申论角度、可能考法
- **AI 辅导对话** — 学习中遇到不懂的知识点，可直接与 AI 对话，获取解释、记忆技巧和关联知识
- **AI 补充卡片** — 对已有卡片批量补充解析、记忆口诀、相关知识点、干扰项等结构化元信息
- **自动错题解释** — 答错时自动调用 AI 生成详细解释和记忆技巧
- **多模型支持** — 可配置主模型、管道模型（文章/卡片生成专用）、精读模型，支持 Fallback 自动切换和 RPM 限速
- **提示词自定义** — 可编辑卡片生成、精读分析、智能导入等功能的 System Prompt

### 📰 文章精读

- **每日推荐** — Dashboard 每日自动推荐一篇未归档的高质量文章（基于当天日期确定性选择，全天不变）
- **多来源抓取** — 支持人民日报、求是网、新华社等多个来源，可自定义添加 RSS/HTML 来源
- **AI 深度分析** — 对文章进行结构化精读分析，标注核心论点、政策要点、金句、申论素材等
- **文章转卡片** — 在阅读中选中任意文段，一键生成闪卡（支持预览编辑后再保存）
- **阅读状态管理** — 新/在读/归档三种状态，支持收藏、批量归档、批量删除
- **多维排序** — 按添加时间、发布日期、质量评分、字数、最近阅读时间排序
- **标签筛选** — 支持按来源、标签、状态多维筛选
- **阅读时间追踪** — 自动记录每篇文章的最后阅读时间，便于追踪阅读进度
- **导入导出** — 支持文章数据的 JSON 导入导出

### 📦 牌组管理

- **灵活组织** — 卡片按牌组（Deck）组织，牌组可归类到分类（Category）
- **学习状态统计** — 每个牌组显示总卡片数及状态分布：待学习（未开始）、学习中（FSRS 学习/再学习状态）、已掌握（FSRS 复习状态）
- **卡片全文搜索** — 在牌组管理页面搜索所有卡片内容，跨牌组定位卡片
- **批量操作** — 批量删除卡片、批量审核 AI 生成卡片
- **标签系统** — 卡片支持多标签，可按标签筛选和组织

### 📊 数据统计

- **学习概览** — Dashboard 显示今日复习进度、连续学习天数、记忆保持率、待复习数量
- **AI 用量统计** — 查看 AI 调用次数、Token 消耗、各功能使用分布、调用成功率
- **学习统计** — 详细的学习数据分析，按时间、分类、难度等维度统计

### 🔄 自动抓取管道

- **定时抓取** — 可配置 Cron 表达式或每日固定时间自动从各来源抓取文章
- **质量过滤** — AI 自动评估文章质量（1-10分），低于阈值的不生成卡片
- **自动分析** — 抓取后自动进行精读分析和卡片生成
- **运行日志** — 详细的抓取执行日志，可查看每次运行的来源数、文章数、卡片数、错误信息
- **RMRB/求是回补** — 支持按日期范围回补人民日报评论和求是网文章

### 📥 导入导出

- **AI 智能导入** — 任意格式文件 AI 自动识别转换，支持分类和纠错
- **格式支持** — CSV、JSON、Excel、Anki .apkg 格式
- **列映射导入** — 非 AI 模式下手动指定列与字段的映射关系
- **数据导出** — 导出卡片和文章数据用于备份或迁移

### ⚙️ 系统功能

- **PWA 支持** — 可安装为桌面/移动端应用，支持离线访问
- **GZip 压缩** — API 响应自动 GZip 压缩（≥500字节），减少数据传输量
- **用户系统** — 注册/登录，JWT 认证，支持管理员角色
- **去重机制** — 卡片导入时自动检测重复内容（基于文本相似度），避免重复录入
- **批量答题提交** — 答题结果本地缓存后批量提交服务器，减少网络请求提升流畅度
- **日志管理** — AI 调用日志、抓取日志、错误日志，支持日志保留期设置
- **设置页面** — 完整的用户设置：AI 配置、学习参数、每日限制、抓取配置等
- **响应式设计** — 完整支持桌面和移动端布局，暂存按钮内嵌在顶部导航栏，不遮挡底部导航和评分按钮

## 技术栈

| 层 | 技术 |
|----------|-------------------------------------------|
| 前端 | Next.js 14, Tailwind CSS, shadcn/ui, Zustand |
| 后端 | Python 3.14+, FastAPI, SQLModel, SQLite, py-fsrs |
| AI | OpenAI 兼容 API（支持任意兼容端点） |
| 容器 | 单 Docker 镜像（多阶段构建） |
| 代理 | Nginx 反向代理（附配置文件） |

## 快速开始

### Docker Compose（推荐）

```yaml
services:
  app:
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    environment:
      - DATABASE_URL=sqlite:////data/anki.db
      - SECRET_KEY=change-me-to-a-random-string
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

```bash
docker compose up -d --build
# 打开 http://localhost:8000
```

### Docker 独立运行

```bash
# 构建
docker build -t anki-app .

# 运行（数据持久化到宿主机）
docker run -d \
  --name anki \
  -p 8000:8000 \
  -v ./data:/data \
  -e DATABASE_URL=sqlite:////data/anki.db \
  -e SECRET_KEY="$(openssl rand -hex 32)" \
  anki-app

# 打开 http://localhost:8000
```

### 本地开发

**前置要求**: Node.js 20+, Python 3.12+

#### Linux / macOS

```bash
chmod +x build.sh
./build.sh            # 构建 + 运行
./build.sh build      # 仅构建
./build.sh run        # 仅运行（构建后）
```

#### Windows

```bat
build.bat             REM 构建 + 运行
build.bat build       REM 仅构建
build.bat run         REM 仅运行（构建后）
```

#### 手动步骤

```bash
# 1. 构建前端
cd frontend
npm ci && npm run build

# 2. 复制静态文件到后端
cp -r out ../backend/static   # Linux/macOS
# xcopy /E /I /Y out ..\backend\static   # Windows

# 3. 安装后端依赖
cd ../backend
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows
pip install -e ".[dev]"

# 4. 启动
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开 http://localhost:8000 使用应用。

## Nginx 反向代理

```bash
# 复制配置到 nginx conf.d
cp nginx-reverse-proxy.conf /path/to/nginx/conf.d/anki.conf

# 确保容器在同一 Docker 网络
docker network create web
docker run -d --name anki --network web -v anki-data:/data anki-app
docker exec nginx nginx -s reload
```

编辑 `anki.conf` 设置你的域名和容器名称。

## 项目结构

```
├── backend/              # FastAPI Python 后端
│   ├── app/
│   │   ├── models/       # SQLModel 数据库模型
│   │   ├── schemas/      # Pydantic 请求/响应模式
│   │   ├── routers/      # API 路由处理器
│   │   ├── services/     # 业务逻辑（FSRS, AI, 抓取管道）
│   │   └── utils/        # 共享工具
│   └── tests/            # pytest 测试套件
├── frontend/             # Next.js 前端（静态导出）
│   ├── src/app/          # 页面（仪表盘、学习、测试等）
│   ├── src/components/   # 可复用 UI 组件
│   └── src/lib/          # API 客户端、状态管理、工具
├── content/              # 预置卡片内容（20个分类 JSON 文件）
├── Dockerfile            # 单容器多阶段构建
├── nginx-reverse-proxy.conf  # Nginx 反向代理配置
├── build.sh              # 构建 + 运行脚本（Linux/macOS）
└── build.bat             # 构建 + 运行脚本（Windows）
```

## 环境变量

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:////data/anki.db` | SQLite 路径（4个斜杠 = 绝对路径） |
| `SECRET_KEY` | 自动生成 | JWT 签名密钥（请设置随机字符串！） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Token 有效期（24小时） |
| `AI_ENABLED` | `false` | 启用 AI 功能 |
| `AI_API_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容 API 端点 |
| `AI_API_KEY` | — | AI 服务 API 密钥 |
| `AI_MODEL` | `gpt-4o-mini` | 默认模型 |
| `AI_MAX_DAILY_CALLS` | `50` | 每日 AI 调用限制 |
| `INGESTION_ENABLED` | `false` | 启用自动抓取 |

## API 核心端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/review/session` | POST | 创建学习会话 |
| `/api/review/due` | POST | 获取到期卡片 |
| `/api/review/answer` | POST | 提交单个答案 |
| `/api/review/batch-answer` | POST | 批量提交答案（学习完成时） |
| `/api/review/preview/batch` | POST | 批量获取卡片评分预览（会话初始化时预加载） |
| `/api/review/stats` | GET | 学习统计数据 |
| `/api/quiz/generate` | POST | 创建模拟测试 |
| `/api/decks` | GET | 牌组列表（含待学/学习中/已掌握统计） |
| `/api/reading` | GET | 文章列表（支持 sort_by=last_read_at 等） |
| `/api/reading/daily-recommendation` | GET | 每日推荐文章 |
| `/api/reading` | POST | 创建文章精读 |
| `/api/ai/generate` | POST | AI 生成卡片 |
| `/api/import-export/import` | POST | 导入卡片（支持 AI 智能模式） |

## 测试

```bash
cd backend
source .venv/bin/activate
pytest                  # 运行所有测试
pytest --cov=app        # 带覆盖率
```

## License

MIT
