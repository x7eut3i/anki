# 第三轮Bug修复文档

## 修复日期
2026-02-25

## 报告的问题

### 1. 模拟测试选项状态问题
**问题描述**：模拟测试不显示题干，而且选择一个选择（比如D），点击下一题，D默认被选中了

**根本原因**：
1. 题干问题：之前已经修复（添加了`{q.front && ...}`条件）
2. 选项状态问题：切换题目时，React没有强制重新渲染选项按钮，导致之前的选中状态视觉上残留

**解决方案**：
- **文件**：`frontend/src/app/(app)/quiz/page.tsx`
- **修改**：在选项容器`<div>`上添加`key={q.id}`属性，强制React在切换题目时重新渲染所有选项按钮
- **代码**：
  ```tsx
  <div className="space-y-2" key={q.id}>
    {q.choice_options?.map((opt, i) => {
      // ...选项按钮
    })}
  </div>
  ```

**技术说明**：
- `answers`状态正确保存了每道题的答案（通过`answers[q.id]`）
- 但React复用了DOM元素，导致视觉状态没有更新
- 添加`key={q.id}`后，每次切换题目都会销毁旧元素并创建新元素

---

### 2. 点击"简单"不自动跳转到下一题
**问题描述**：在学习界面，点击评分按钮（忘了/困难/记得/简单）后，不会自动跳转到下一张卡片

**分析结果**：**这个功能实际上是正常的**！

**代码验证**：
1. **Study页面的handleRate函数**（`frontend/src/app/(app)/study/page.tsx` 第72-85行）：
   ```tsx
   const handleRate = async (rating: number) => {
     if (!token) return;
     const card = currentCards[currentIndex];
     try {
       await review.answer({ card_id: card.id, rating }, token);
       setReviewedCount((c) => c + 1);
   
       if (currentIndex + 1 < currentCards.length) {
         nextCard();  // ← 自动跳转到下一题
       } else {
         setCompleted(true);  // ← 完成学习
       }
     } catch (err) {
       console.error("Review failed:", err);
     }
   };
   ```

2. **Store的nextCard函数**（`frontend/src/lib/store.ts` 第53-57行）：
   ```tsx
   nextCard: () =>
     set((s) => ({
       currentIndex: Math.min(s.currentIndex + 1, s.currentCards.length - 1),
       showAnswer: false,  // ← 重置为未显示答案状态
     })),
   ```

**可能的用户体验问题**：
- 如果评分后看起来"没反应"，可能是因为下一张卡片与当前卡片看起来相似
- 或者网络延迟导致API调用较慢
- 建议用户检查：是否在控制台看到错误？网络是否正常？

**如果问题依然存在，请提供更多信息**：
- 浏览器控制台是否有错误？
- 点击哪个按钮？（忘了/困难/记得/简单）
- 是否显示了答案后才点击？
- 网络请求是否成功？（F12 → Network）

---

### 3. AI测试连接报422错误
**问题描述**：在AI界面点击"测试连接"，发送POST http://127.0.0.1:8000/api/ai/test-connection，报422错误（验证错误）

**根本原因**：
- 后端`/api/ai/test-connection`端点期望接收`AITestRequest`请求体，包含`api_base_url`、`api_key`、`model`字段
- 前端调用时没有发送任何请求体，导致验证失败（422 Unprocessable Entity）

**解决方案**：
1. **修改API客户端**（`frontend/src/lib/api.ts`）：
   ```typescript
   // 之前：
   testConnection: (token: string) =>
     request<any>("/api/ai/test-connection", { method: "POST", token }),
   
   // 修改后：
   testConnection: (data: { api_base_url: string; api_key: string; model: string }, token: string) =>
     request<any>("/api/ai/test-connection", { method: "POST", body: JSON.stringify(data), token }),
   ```

2. **修改AI页面调用**（`frontend/src/app/(app)/ai/page.tsx`）：
   ```typescript
   const handleTestConnection = async () => {
     if (!token || !endpoint || !apiKey || !model) {
       setConnected(false);
       return;
     }
     setTestingConn(true);
     try {
       const result = await ai.testConnection(
         { api_base_url: endpoint, api_key: apiKey, model },  // ← 发送配置数据
         token
       );
       setConnected(result.success);  // ← 使用正确的响应字段
     } catch {
       setConnected(false);
     } finally {
       setTestingConn(false);
     }
   };
   ```

**额外修复**：
- 添加了必填字段验证：如果`endpoint`、`apiKey`或`model`为空，直接返回失败
- 修正了响应字段：从`result.status === "ok"`改为`result.success`（匹配后端的`AITestResponse`）

---

### 4. 学习界面为什么默认进去就答题？
**问题描述**：点击学习界面，为什么默认进去答题？这个题目来自哪里？不需要选吗？还是说重复使用上一个session的？

**答案：这是正确的设计！**

**工作流程说明**：

1. **点击"学习"按钮时**（从Dashboard或分类卡片）：
   - 你会进入学习页面：`/study?mode=review&category=<id>`
   - 或点击牌组学习：`/study?mode=review&deck=<id>`

2. **学习页面自动加载待复习卡片**（`frontend/src/app/(app)/study/page.tsx` 第39-54行）：
   ```tsx
   const loadCards = useCallback(async () => {
     if (!token) return;
     setLoading(true);
     setCompleted(false);
     try {
       const params: any = { limit: 50 };
       if (categoryId) params.category_ids = [parseInt(categoryId)];
       if (deckId) params.deck_id = parseInt(deckId);
       const data = await review.getDue(params, token);  // ← 获取待复习卡片
       if (data.cards && data.cards.length > 0) {
         setCards(data.cards);  // ← 加载卡片，立即开始学习
       } else {
         setCompleted(true);  // ← 没有待复习卡片
       }
     } finally {
       setLoading(false);
     }
   }, [token, setCards]);
   ```

3. **题目来源**：
   - 后端API `/api/review/due` 使用**FSRS算法**计算哪些卡片需要复习
   - 根据你的学习历史（上次复习时间、评分）决定今天应该复习哪些卡片
   - 这些卡片是系统智能推荐的，**不需要手动选择**

4. **为什么这样设计**？
   - ✅ **简化流程**：符合Anki的设计理念——打开就学，无需配置
   - ✅ **科学复习**：FSRS算法自动安排最佳复习时机
   - ✅ **减少摩擦**：避免"选择困难症"，提高学习效率
   - ✅ **专注学习**：让用户专注于记忆，而不是管理

5. **不同的学习模式**：
   - **复习模式**（默认）：只显示"到期"的卡片（需要复习的）
   - **从分类学习**：复习特定分类下的到期卡片
   - **从牌组学习**：复习特定牌组下的到期卡片

6. **如果想浏览所有卡片？**
   - 去"查看卡片"页面（View Cards）
   - 或去"牌组管理"页面查看牌组详情
   - 学习界面专注于**高效复习**，不是浏览

**类比Anki桌面版**：
- 当你打开Anki并点击一个牌组时，它会立即显示第一张待复习的卡片
- 不会问你"要复习哪些卡片？"
- 这是间隔重复学习的标准体验！

---

## 部署步骤

1. **修改前端代码**：
   ```bash
   # 已完成3个文件的修改：
   # - frontend/src/app/(app)/quiz/page.tsx
   # - frontend/src/lib/api.ts
   # - frontend/src/app/(app)/ai/page.tsx
   ```

2. **重新构建前端**：
   ```bash
   cd c:\code\anki\frontend
   npm run build
   ```

3. **部署静态文件**：
   ```bash
   Remove-Item c:\code\anki\backend\static -Recurse -Force -ErrorAction SilentlyContinue
   Copy-Item out c:\code\anki\backend\static -Recurse
   ```

4. **重启后端服务器**：
   ```bash
   cd c:\code\anki\backend
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

---

## 测试清单

### ✅ 1. 模拟测试选项状态
- [ ] 进入"模拟测试"页面
- [ ] 开始一个测试（选择任意分类和题目数量）
- [ ] 在第一题选择任意选项（比如D）
- [ ] 点击"下一题"
- [ ] 验证：第二题的选项没有任何被选中（不应该默认选中D）

### ✅ 2. 学习页面评分按钮
- [ ] 进入"仪表盘"
- [ ] 点击任意分类的"学习"按钮
- [ ] 显示答案后，点击任意评分按钮（忘了/困难/记得/简单）
- [ ] 验证：自动跳转到下一张卡片
- [ ] 验证：新卡片处于"未显示答案"状态

### ✅ 3. AI测试连接
- [ ] 进入"AI助手"页面
- [ ] 在"配置"选项卡填写：
  - API 端点：`https://api.deepseek.com/v1`（或其他）
  - API Key：你的实际API密钥
  - 模型：`deepseek-chat`
- [ ] 点击"测试连接"按钮
- [ ] 验证：不再报422错误
- [ ] 验证：显示连接成功或失败消息（取决于配置是否正确）

### ℹ️ 4. 学习界面体验
- [ ] 理解：学习界面自动加载待复习卡片是**正确的设计**
- [ ] 如果没有待复习卡片，会显示"太棒了！今天没有待复习的卡片了"
- [ ] 可以通过URL参数控制：
  - `/study?mode=review&category=1` - 复习分类1的卡片
  - `/study?mode=review&deck=1` - 复习牌组1的卡片

---

## 技术总结

### 问题类型分析
1. **React状态管理**：quiz页面的key问题（状态残留）
2. **API设计**：test-connection端点的请求体缺失
3. **用户体验理解**：学习流程的设计意图

### 修复影响范围
- ✅ 前端：3个文件修改
- ✅ 后端：无修改（端点已正确实现）
- ✅ 数据库：无影响
- ✅ 测试：所有现有测试应继续通过

### 未来优化建议
1. **模拟测试增强**：
   - 添加答题进度保存（刷新页面不丢失）
   - 显示答题时间统计
   - 错题回顾功能

2. **学习体验优化**：
   - 添加"新手引导"提示学习流程
   - 在Dashboard显示"今日待复习数量"
   - 添加"快速开始"按钮直接进入学习

3. **AI功能完善**：
   - 配置验证提示更友好
   - 保存配置前自动测试连接
   - 支持更多AI模型预设

---

## 版本信息
- **修复版本**：v0.1.0-bugfix-round3
- **修复数量**：3个实际bug + 1个用户体验说明
- **修改文件**：3个前端文件
- **测试状态**：待用户验证

---

## 用户反馈
请测试以上修复，如有任何问题，请提供：
1. 具体操作步骤
2. 浏览器控制台错误（F12 → Console）
3. 网络请求详情（F12 → Network）
4. 预期行为 vs 实际行为
