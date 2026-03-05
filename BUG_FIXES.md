# Bug 修复记录 - 2026-02-25

## ✅ 已修复的问题

### 1️⃣ 点击「记得」不进入下一题
**问题**: 评分按钮点击后卡片没有切换到下一题

**修复**:
- `Flashcard` 组件添加 `useEffect` 监听 `card.id` 变化，自动重置 `selectedChoice`
- 确保每次切换卡片时，选择状态都被清除

**文件**: [frontend/src/components/flashcard.tsx](frontend/src/components/flashcard.tsx)

---

### 2️⃣ true_false 题不显示选项
**问题**: 判断题（对错题）不显示「正确」「错误」选项

**修复**:
- 优先处理 `true_false` 类型，生成默认选项 `["正确", "错误"]`
- 支持从 `choices` JSON 字段解析自定义选项
- 确保选项在卡片加载时立即显示

**文件**: [frontend/src/components/flashcard.tsx](frontend/src/components/flashcard.tsx)

---

### 3️⃣ 模拟测试不显示题干
**问题**: Quiz 页面题目的 `front` 字段可能为空

**修复**:
- 添加 `q.front &&` 条件判断
- 只在题干存在时才渲染 `<p>` 标签
- 避免显示空白题目

**文件**: [frontend/src/app/(app)/quiz/page.tsx](frontend/src/app/(app)/quiz/page.tsx)

---

### 4️⃣ Dashboard 科目分类卡片数目显示为 0
**问题**: 所有 category 的 `card_count` 都是 0

**修复**:
- 后端 `list_categories` API 动态计算每个分类的卡片数
- 使用 SQL `COUNT` 查询当前用户在该分类下的卡片数
- 返回包含 `card_count` 的完整分类信息

**文件**: [backend/app/routers/categories.py](backend/app/routers/categories.py)

**代码**:
```python
from sqlmodel import func
from app.models.card import Card

for cat in cats:
    cat_dict = cat.model_dump()
    card_count = session.exec(
        select(func.count(Card.id)).where(
            Card.category_id == cat.id,
            Card.user_id == current_user.id
        )
    ).one()
    cat_dict["card_count"] = card_count
    result.append(cat_dict)
```

---

### 5️⃣ 牌组管理 UI 显示两个图标和两次名字
**问题**: Deck 卡片同时显示：
- 左侧大图标 + category 名字（在 Badge 中）
- 右侧又显示一次 category 名字

**修复**:
- 移除独立的大图标 `<span>`
- 将图标合并到 Badge 中：`{getCatIcon()} {getCatName()}`
- 简化为单行显示：牌组名 + (分类图标+名字 Badge)

**文件**: [frontend/src/app/(app)/decks/page.tsx](frontend/src/app/(app)/decks/page.tsx)

**修复后**:
```tsx
<div>
  <CardTitle>{deck.name}</CardTitle>
  {deck.category_id && (
    <Badge>
      {getCatIcon(deck.category_id)} {getCatName(deck.category_id)}
    </Badge>
  )}
</div>
```

---

### 6️⃣ AI 测试连接报 405 错误
**问题**: 前端调用 `POST /api/ai/test-connection`，但后端路由是 `/test`

**修复**:
- 修改后端路由从 `@router.post("/test")` 改为 `@router.post("/test-connection")`
- 保持与前端 API 调用一致

**文件**: [backend/app/routers/ai.py](backend/app/routers/ai.py)

---

## 📋 测试清单

启动服务器后测试：

```bash
# 后端
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000

- [ ] **Dashboard**: 科目卡片显示正确的卡片数（161张已导入）
- [ ] **学习页面**: 
  - [ ] 选择题显示 A/B/C/D 选项
  - [ ] 判断题显示「正确」「错误」选项
  - [ ] 选择后自动显示答案（绿色=正确，红色=错误）
  - [ ] 点击「记得」后进入下一题
- [ ] **模拟测试**: 
  - [ ] 题干正确显示
  - [ ] 选项可点击
  - [ ] 进度条正常
- [ ] **牌组管理**: 
  - [ ] 每个牌组只显示一个图标
  - [ ] Category 名字只显示一次（在 Badge 中）
  - [ ] 点击「查看卡片」跳转到 deck-detail 页面
- [ ] **AI 设置**: 
  - [ ] 测试连接按钮不再报 405 错误

---

## 🔧 技术细节

### 前端修复
1. **状态管理**: 卡片切换时正确重置选择状态
2. **条件渲染**: 防御性检查避免空数据导致的 UI 错误
3. **数据解析**: 兼容多种数据格式（JSON 字符串、数组、默认值）

### 后端修复
1. **动态计算**: Category API 实时计算卡片数，避免数据不一致
2. **路由一致性**: 确保 API 路径与前端调用匹配

### 数据库现状
- **161 张卡片**: 已通过 `content/import_content.py` 导入
- **20 个分类**: 覆盖公务员考试所有科目
- **20 个牌组**: 自动创建，与分类一一对应
- **1 个用户**: admin / admin123

---

## 📝 部署说明

所有修复已构建并复制到 `backend/static/`：

```bash
cd frontend
npm run build
rm -rf ../backend/static
cp -r out ../backend/static
```

服务器会自动 reload，无需手动重启。
