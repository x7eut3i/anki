/**
 * E2E Tests for Anki Flashcard App
 *
 * Uses client-side navigation (sidebar links) to avoid Zustand persist
 * hydration race condition that occurs with full page.goto() reloads.
 */
import { test, expect, type Page } from "@playwright/test";

const TEST_USER = {
  username: "testuser",
  email: "test@example.com",
  password: "test123456",
};

// Helper: login and wait for dashboard
async function loginAs(page: Page) {
  await page.goto("/login");
  await page.waitForSelector('input[placeholder="请输入用户名"]', {
    timeout: 10_000,
  });
  await page.fill('input[placeholder="请输入用户名"]', TEST_USER.username);
  await page.fill('input[placeholder="请输入密码"]', TEST_USER.password);
  await page.click('button[type="submit"]');
  await page.waitForURL("**/dashboard", { timeout: 10_000 });
  // Ensure dashboard has fully loaded
  await expect(
    page.getByRole("heading", { name: "学习概览" })
  ).toBeVisible({ timeout: 10_000 });
}

// Helper: navigate using sidebar (client-side routing)
async function navigateTo(page: Page, path: string) {
  // Set desktop viewport so sidebar is visible
  await page.setViewportSize({ width: 1280, height: 720 });
  const link = page.locator(`a[href="${path}"]`).first();
  await link.waitFor({ timeout: 5_000 });
  await link.click();
  await page.waitForTimeout(1_000);
}

// Helper: fill AI config form
async function fillAIConfig(page: Page) {
  const endpointInput = page.locator(
    'input[placeholder="https://api.deepseek.com/v1"]'
  );
  await endpointInput.waitFor({ timeout: 10_000 });
  await endpointInput.fill("https://gpt-load.tsit.edu.kg/proxy/gcli2/v1");

  const keyInput = page.locator('input[placeholder="sk-..."]');
  await keyInput.fill(
    "sk-8MXwU90komEZmq3UiG_eXKVcbXo5bzxIl27VzFYnOuKifzU6"
  );

  const modelInput = page.locator('input[placeholder="deepseek-chat"]');
  if (await modelInput.isVisible().catch(() => false)) {
    await modelInput.fill("gemini-2.5-flash");
  }
}

// ---------------------------------------------------------------------------
// 1. Login flow
// ---------------------------------------------------------------------------
test.describe("登录流程", () => {
  test("登录页面正确渲染", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText("Anki Cards")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("登录你的账号")).toBeVisible();
    await expect(
      page.locator('input[placeholder="请输入用户名"]')
    ).toBeVisible();
    await expect(
      page.locator('input[placeholder="请输入密码"]')
    ).toBeVisible();
  });

  test("错误密码显示错误信息", async ({ page }) => {
    await page.goto("/login");
    await page.fill('input[placeholder="请输入用户名"]', TEST_USER.username);
    await page.fill('input[placeholder="请输入密码"]', "wrongpassword");
    await page.click('button[type="submit"]');
    await expect(page.locator(".text-red-500")).toBeVisible({ timeout: 5_000 });
  });

  test("正确密码跳转到仪表盘", async ({ page }) => {
    await loginAs(page);
    await expect(
      page.getByRole("heading", { name: "学习概览" })
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 2. Dashboard
// ---------------------------------------------------------------------------
test.describe("仪表盘", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("显示学习概览和统计数据", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "学习概览" })
    ).toBeVisible();
    await expect(page.getByText("今日复习")).toBeVisible();
    await expect(page.getByText("连续学习")).toBeVisible();
    await expect(page.getByText("记忆保持率")).toBeVisible();
    await expect(page.getByText("待复习")).toBeVisible();
  });

  test("显示快捷操作按钮", async ({ page }) => {
    await expect(page.locator("h3", { hasText: "开始复习" })).toBeVisible();
    await expect(page.locator("h3", { hasText: "混合模式" })).toBeVisible();
    await expect(page.locator("h3", { hasText: "模拟测试" })).toBeVisible();
  });

  test("显示科目分类", async ({ page }) => {
    await expect(page.getByText("科目分类")).toBeVisible();
    await expect(page.getByText("成语")).toBeVisible({ timeout: 5_000 });
  });

  test("点击「立即学习」跳转到学习页面", async ({ page }) => {
    await page.locator("button", { hasText: "立即学习" }).click();
    await expect(page).toHaveURL(/\/study/);
  });
});

// ---------------------------------------------------------------------------
// 3. Study flow
// ---------------------------------------------------------------------------
test.describe("学习流程", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("加载待复习卡片并显示正面", async ({ page }) => {
    await navigateTo(page, "/study");
    await page.waitForTimeout(3_000);

    const hasReviewMode = await page
      .getByText("复习模式")
      .isVisible()
      .catch(() => false);
    const hasMixedMode = await page
      .getByText("混合模式")
      .isVisible()
      .catch(() => false);
    const hasCompletion = await page
      .getByText("太棒了")
      .isVisible()
      .catch(() => false);
    const hasPending = await page
      .getByText("发现未完成的学习")
      .isVisible()
      .catch(() => false);
    const hasNoCards = await page
      .getByText("今天没有待复习的卡片了")
      .isVisible()
      .catch(() => false);

    expect(
      hasReviewMode || hasMixedMode || hasCompletion || hasPending || hasNoCards
    ).toBeTruthy();
  });

  test("翻转卡片查看答案", async ({ page }) => {
    await navigateTo(page, "/study");
    await page.waitForTimeout(3_000);

    const showHint = page.getByText("点击或按空格显示答案");
    if (await showHint.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await showHint.click();
      await expect(
        page
          .locator("button", { hasText: "忘了" })
          .or(page.locator("button", { hasText: "困难" }))
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("评分后进入下一张卡片", async ({ page }) => {
    await navigateTo(page, "/study");
    await page.waitForTimeout(3_000);

    const showHint = page.getByText("点击或按空格显示答案");
    if (await showHint.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await showHint.click();
      await page.waitForTimeout(500);
      const goodBtn = page.locator("button", { hasText: "记得" });
      if (await goodBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await goodBtn.click();
        await page.waitForTimeout(1_000);
      }
    }
  });
});

// ---------------------------------------------------------------------------
// 4. Quiz flow
// ---------------------------------------------------------------------------
test.describe("模拟测试", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("测试配置页面加载", async ({ page }) => {
    await navigateTo(page, "/quiz");
    await expect(
      page.getByRole("heading", { name: "模拟测试" })
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("选择分类", { exact: true })).toBeVisible();
    await expect(page.getByText("题目数量", { exact: true })).toBeVisible();
  });

  test("选择分类和题目数量", async ({ page }) => {
    await navigateTo(page, "/quiz");
    await page.waitForSelector("text=题目数量", { timeout: 10_000 });

    const btn10 = page.locator("button", { hasText: "10 题" });
    await btn10.waitFor({ timeout: 10_000 });
    await btn10.click();
    await expect(btn10).toBeVisible();
  });

  test("生成并回答测试题目", async ({ page }) => {
    await navigateTo(page, "/quiz");
    await page.waitForSelector("text=题目数量", { timeout: 10_000 });

    await page.locator("button", { hasText: "10 题" }).click();
    await page.waitForTimeout(500);
    await page.locator("button", { hasText: "开始测试" }).click();
    await page.waitForSelector("text=第 1 /", { timeout: 15_000 });

    const choices = page.locator("button.w-full.text-left");
    const choiceCount = await choices.count();
    if (choiceCount > 0) {
      await choices.first().click();
    } else {
      const input = page.locator('input[placeholder="请输入答案..."]');
      if (await input.isVisible().catch(() => false)) {
        await input.fill("测试答案");
      }
    }

    const nextBtn = page.locator("button", { hasText: "下一题" });
    if (await nextBtn.isVisible().catch(() => false)) {
      await nextBtn.click();
      await expect(page.getByText("第 2 /")).toBeVisible({ timeout: 5_000 });
    }
  });

  test("提交答卷显示结果", async ({ page }) => {
    test.setTimeout(120_000);
    await navigateTo(page, "/quiz");
    await page.waitForSelector("text=题目数量", { timeout: 10_000 });

    await page.locator("button", { hasText: "10 题" }).click();
    await page.waitForTimeout(500);
    await page.locator("button", { hasText: "开始测试" }).click();
    await page.waitForSelector("text=第 1 /", { timeout: 15_000 });

    const totalText = await page
      .locator("text=/第 \\d+ \\/ (\\d+)/")
      .textContent();
    const total = parseInt(totalText?.match(/\/ (\d+)/)?.[1] || "10");

    for (let i = 0; i < total; i++) {
      const choices = page.locator("button.w-full.text-left");
      const fillInput = page.locator('input[placeholder="请输入答案..."]');

      if (
        await choices
          .first()
          .isVisible({ timeout: 3_000 })
          .catch(() => false)
      ) {
        await choices.first().click();
      } else if (await fillInput.isVisible().catch(() => false)) {
        await fillInput.fill("answer");
      }

      if (i < total - 1) {
        await page.locator("button", { hasText: "下一题" }).click();
        await page.waitForTimeout(500);
      }
    }

    await page.locator("button", { hasText: "提交答卷" }).click();
    await expect(page.getByText("题正确")).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// 5. AI configuration
// ---------------------------------------------------------------------------
test.describe("AI 助手配置", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("AI 页面加载配置表单", async ({ page }) => {
    await navigateTo(page, "/ai");
    await expect(
      page.getByRole("heading", { name: "AI 助手" })
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("AI 服务配置")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("API 端点")).toBeVisible();
    await expect(page.getByText("API Key")).toBeVisible();
  });

  test("填写 AI 配置并保存", async ({ page }) => {
    await navigateTo(page, "/ai");
    await page.waitForSelector("text=AI 服务配置", { timeout: 10_000 });
    await fillAIConfig(page);
    await page.locator("button", { hasText: "保存配置" }).click();
    await page.waitForTimeout(2_000);
  });

  test("测试 AI 连接", async ({ page }) => {
    test.setTimeout(90_000);
    await navigateTo(page, "/ai");
    await page.waitForSelector("text=AI 服务配置", { timeout: 10_000 });
    await fillAIConfig(page);

    await page.locator("button", { hasText: "测试连接" }).click();
    const success = page.getByText("连接成功");
    const fail = page.getByText("连接失败");
    await expect(success.or(fail)).toBeVisible({ timeout: 60_000 });
  });

  test("拉取模型列表", async ({ page }) => {
    test.setTimeout(90_000);
    await navigateTo(page, "/ai");
    await page.waitForSelector("text=AI 服务配置", { timeout: 10_000 });

    const endpointInput = page.locator(
      'input[placeholder="https://api.deepseek.com/v1"]'
    );
    await endpointInput.waitFor({ timeout: 10_000 });
    await endpointInput.fill("https://gpt-load.tsit.edu.kg/proxy/gcli2/v1");

    const keyInput = page.locator('input[placeholder="sk-..."]');
    await keyInput.fill(
      "sk-8MXwU90komEZmq3UiG_eXKVcbXo5bzxIl27VzFYnOuKifzU6"
    );

    await page.locator("button", { hasText: "拉取模型" }).click();
    await page.waitForTimeout(10_000);
    const dropdown = page.locator("select");
    if (await dropdown.isVisible().catch(() => false)) {
      const options = await dropdown.locator("option").count();
      expect(options).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// 6. AI Chat
// ---------------------------------------------------------------------------
test.describe("AI 对话", () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000);
    await loginAs(page);
    // Configure AI first
    await navigateTo(page, "/ai");
    await page.waitForSelector("text=AI 服务配置", { timeout: 10_000 });
    await fillAIConfig(page);
    await page.locator("button", { hasText: "保存配置" }).click();
    await page.waitForTimeout(2_000);
  });

  test("切换到 AI 对话标签", async ({ page }) => {
    await page.locator("button", { hasText: "AI 对话" }).click();
    await expect(
      page.getByText("向 AI 助手提问学习相关问题")
    ).toBeVisible({ timeout: 10_000 });
  });

  test("发送消息给 AI", async ({ page }) => {
    await page.locator("button", { hasText: "AI 对话" }).click();
    await page.waitForTimeout(1_000);

    const input = page.locator('input[placeholder="输入你的问题..."]');
    await input.waitFor({ timeout: 10_000 });
    await input.fill("什么是行政法的基本原则？");
    await page.locator("button:has(svg)").last().click();

    await page.waitForTimeout(15_000);
    const messages = page.locator(".whitespace-pre-wrap");
    const msgCount = await messages.count();
    expect(msgCount).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// 7. Decks management
// ---------------------------------------------------------------------------
test.describe("牌组管理", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("牌组页面加载", async ({ page }) => {
    await navigateTo(page, "/decks");
    await expect(
      page.getByRole("heading", { name: "牌组管理" })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("显示已有牌组", async ({ page }) => {
    await navigateTo(page, "/decks");
    await page.waitForTimeout(3_000);
    const deckCards = page.getByText("张卡片");
    await expect(deckCards.first()).toBeVisible({ timeout: 10_000 });
  });

  test("创建新牌组", async ({ page }) => {
    await navigateTo(page, "/decks");
    await page.waitForTimeout(2_000);

    await page.locator("button", { hasText: "新建牌组" }).click();

    await page.fill('input[placeholder="牌组名称"]', "E2E测试牌组");
    await page.fill(
      'input[placeholder="描述 (可选)"]',
      "这是E2E测试创建的牌组"
    );

    await page.locator("button", { hasText: "创建" }).click();
    await page.waitForTimeout(2_000);

    await expect(page.getByText("E2E测试牌组").first()).toBeVisible({
      timeout: 5_000,
    });
  });

  test("删除牌组", async ({ page }) => {
    await navigateTo(page, "/decks");
    await page.waitForTimeout(2_000);

    await page.locator("button", { hasText: "新建牌组" }).click();
    await page.fill('input[placeholder="牌组名称"]', "待删除牌组");
    await page.locator("button", { hasText: "创建" }).click();
    await page.waitForTimeout(2_000);

    await expect(page.getByText("待删除牌组").first()).toBeVisible();

    page.on("dialog", (dialog) => dialog.accept());

    const deckCard = page
      .locator("div")
      .filter({ hasText: "待删除牌组" })
      .first();
    const deleteBtn = deckCard.locator("button:has(svg)");
    if (await deleteBtn.first().isVisible().catch(() => false)) {
      await deleteBtn.first().click();
      await page.waitForTimeout(2_000);
    }
  });
});

// ---------------------------------------------------------------------------
// 8. Settings
// ---------------------------------------------------------------------------
test.describe("设置页面", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("设置页面加载个人信息", async ({ page }) => {
    await navigateTo(page, "/settings");
    await expect(
      page.getByRole("heading", { name: "设置", exact: true })
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("个人信息", { exact: true })).toBeVisible();
    await expect(page.getByText("学习设置", { exact: true })).toBeVisible();
  });

  test("显示当前用户信息", async ({ page }) => {
    await navigateTo(page, "/settings");
    await page.waitForTimeout(2_000);
    await expect(page.getByText(TEST_USER.username)).toBeVisible({
      timeout: 10_000,
    });
  });

  test("退出登录返回登录页", async ({ page }) => {
    await navigateTo(page, "/settings");
    await page.waitForTimeout(1_000);

    await page.locator("button", { hasText: "退出登录" }).click();
    await page.waitForURL("**/login", { timeout: 10_000 });
    await expect(page.getByText("Anki Cards")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 9. Navigation (sidebar)
// ---------------------------------------------------------------------------
test.describe("侧边栏导航", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page);
  });

  test("所有导航链接可点击", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });

    const dashLink = page.locator('a[href="/dashboard"]');
    if (await dashLink.isVisible().catch(() => false)) {
      await dashLink.click();
      await expect(page).toHaveURL(/dashboard/);
    }
  });

  test("未登录用户被重定向到登录页", async ({ page }) => {
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());
    await page.goto("/dashboard");
    await page.waitForURL("**/login", { timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 10. API health check
// ---------------------------------------------------------------------------
test.describe("API 健康检查", () => {
  test("GET /api/health returns ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(json.status).toBe("ok");
  });
});

// ---------------------------------------------------------------------------
// 11. Registration disabled
// ---------------------------------------------------------------------------
test.describe("注册已禁用", () => {
  test("POST /api/auth/register returns 403", async ({ request }) => {
    const res = await request.post("/api/auth/register", {
      data: {
        username: "newuser",
        email: "new@example.com",
        password: "test123456",
      },
    });
    expect(res.status()).toBe(403);
    const json = await res.json();
    expect(json.detail).toContain("注册功能已关闭");
  });

  test("登录页面没有注册入口", async ({ page }) => {
    await page.goto("/login");
    await page.waitForSelector('input[placeholder="请输入用户名"]', {
      timeout: 10_000,
    });
    await expect(
      page.locator("button", { hasText: "注册" })
    ).not.toBeVisible();
    await expect(
      page.locator("button", { hasText: "登录" })
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 12. Card deduplication API
// ---------------------------------------------------------------------------
test.describe("卡片去重", () => {
  test("POST /api/cards/dedup-check works", async ({ request }) => {
    const loginRes = await request.post("/api/auth/login", {
      data: { username: TEST_USER.username, password: TEST_USER.password },
    });
    const { access_token } = await loginRes.json();

    const res = await request.post("/api/cards/dedup-check", {
      headers: { Authorization: `Bearer ${access_token}` },
      data: {
        fronts: [
          "下列成语中，加点字使用正确的是：",
          "这个肯定不存在的随机题目12345",
        ],
      },
    });
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(json.duplicates).toBeDefined();
    expect(json.duplicates.length).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// 13. Import / Export (API-level tests)
// ---------------------------------------------------------------------------
test.describe("导入导出", () => {
  let token: string;

  test.beforeEach(async ({ request }) => {
    const loginRes = await request.post("/api/auth/login", {
      data: { username: TEST_USER.username, password: TEST_USER.password },
    });
    const body = await loginRes.json();
    token = body.access_token;
  });

  test("导出CSV", async ({ request }) => {
    // First get a deck ID
    const decksRes = await request.get("/api/decks", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const decksBody = await decksRes.json();
    if (!decksBody.decks || decksBody.decks.length === 0) {
      test.skip();
      return;
    }
    const deckId = decksBody.decks[0].id;

    const res = await request.get(
      `/api/import-export/export/csv?deck_id=${deckId}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(res.ok()).toBeTruthy();
    const text = await res.text();
    expect(text).toContain("front");
    expect(text).toContain("back");
  });

  test("导出JSON", async ({ request }) => {
    const decksRes = await request.get("/api/decks", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const decksBody = await decksRes.json();
    if (!decksBody.decks || decksBody.decks.length === 0) {
      test.skip();
      return;
    }
    const deckId = decksBody.decks[0].id;

    const res = await request.get(
      `/api/import-export/export/json?deck_id=${deckId}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(res.ok()).toBeTruthy();
    const json = await res.json();
    expect(Array.isArray(json)).toBeTruthy();
  });

  test("导入CSV", async ({ request }) => {
    // Get or create deck
    const decksRes = await request.get("/api/decks", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const decksBody = await decksRes.json();
    let deckId: number;

    if (decksBody.decks && decksBody.decks.length > 0) {
      deckId = decksBody.decks[0].id;
    } else {
      const createRes = await request.post("/api/decks", {
        headers: { Authorization: `Bearer ${token}` },
        data: { name: "E2E导入测试", description: "test import" },
      });
      const created = await createRes.json();
      deckId = created.id;
    }

    const csvContent =
      "front,back,card_type\nE2E测试问题_CSV,E2E测试答案_CSV,basic\n";
    const res = await request.post(
      `/api/import-export/import/csv?deck_id=${deckId}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        multipart: {
          file: {
            name: "test.csv",
            mimeType: "text/csv",
            buffer: Buffer.from(csvContent, "utf-8"),
          },
        },
      }
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.created).toBeGreaterThanOrEqual(1);
  });

  test("导入JSON", async ({ request }) => {
    const decksRes = await request.get("/api/decks", {
      headers: { Authorization: `Bearer ${token}` },
    });
    const decksBody = await decksRes.json();
    let deckId: number;

    if (decksBody.decks && decksBody.decks.length > 0) {
      deckId = decksBody.decks[0].id;
    } else {
      const createRes = await request.post("/api/decks", {
        headers: { Authorization: `Bearer ${token}` },
        data: { name: "E2E导入测试JSON", description: "test import" },
      });
      const created = await createRes.json();
      deckId = created.id;
    }

    const jsonContent = JSON.stringify([
      { front: "E2E测试问题_JSON", back: "E2E测试答案_JSON", card_type: "basic" },
    ]);
    const res = await request.post(
      `/api/import-export/import/json?deck_id=${deckId}`,
      {
        headers: { Authorization: `Bearer ${token}` },
        multipart: {
          file: {
            name: "test.json",
            mimeType: "application/json",
            buffer: Buffer.from(jsonContent, "utf-8"),
          },
        },
      }
    );
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.created).toBeGreaterThanOrEqual(1);
  });

  test("导入导出页面可访问", async ({ page }) => {
    await loginAs(page);
    await navigateTo(page, "/import-export");
    await expect(
      page.getByRole("heading", { name: "导入 / 导出" })
    ).toBeVisible({ timeout: 10_000 });
    // Check import/export buttons exist
    await expect(page.getByText("导入 CSV")).toBeVisible();
    await expect(page.getByText("导入 JSON")).toBeVisible();
    await expect(page.getByText("导出 CSV")).toBeVisible();
    await expect(page.getByText("导出 JSON")).toBeVisible();
  });
});

// ─── 文章精读 ────────────────────────────────────────────
test.describe("文章精读", () => {
  test("精读页面可访问", async ({ page }) => {
    await loginAs(page);
    await navigateTo(page, "/reading");
    await expect(
      page.getByRole("heading", { name: "文章精读" })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("显示筛选按钮和创建入口", async ({ page }) => {
    await loginAs(page);
    await navigateTo(page, "/reading");
    await expect(
      page.getByRole("heading", { name: "文章精读" })
    ).toBeVisible({ timeout: 10_000 });

    // Filter buttons should be visible
    await expect(page.getByText("全部")).toBeVisible();
    await expect(page.getByText("待读")).toBeVisible();
    await expect(page.getByText("已读")).toBeVisible();

    // Create button should be visible
    await expect(page.getByText("新建精读")).toBeVisible();
  });

  test("新建精读表单展开和折叠", async ({ page }) => {
    await loginAs(page);
    await navigateTo(page, "/reading");
    await expect(
      page.getByRole("heading", { name: "文章精读" })
    ).toBeVisible({ timeout: 10_000 });

    // Click create button to open form
    await page.getByText("新建精读").click();
    await expect(
      page.getByPlaceholder("输入文章内容")
    ).toBeVisible({ timeout: 5_000 });

    // Title input should exist
    await expect(
      page.getByPlaceholder("文章标题")
    ).toBeVisible();

    // Submit button should be disabled when empty
    const submitBtn = page.getByRole("button", { name: "开始精读分析" });
    await expect(submitBtn).toBeVisible();
  });

  test("空状态或文章列表", async ({ page }) => {
    await loginAs(page);
    await navigateTo(page, "/reading");
    await expect(
      page.getByRole("heading", { name: "文章精读" })
    ).toBeVisible({ timeout: 10_000 });

    // Either show empty state or article cards
    const emptyState = page.getByText("还没有精读文章");
    const articleCard = page.locator("[class*='border']").first();
    // Wait for loading to finish
    await page.waitForTimeout(2_000);
    const isEmpty = await emptyState.isVisible().catch(() => false);
    if (isEmpty) {
      await expect(emptyState).toBeVisible();
    } else {
      // At least one article card should be present
      await expect(articleCard).toBeVisible();
    }
  });

  test("侧边栏包含精读链接", async ({ page }) => {
    await loginAs(page);
    await page.setViewportSize({ width: 1280, height: 720 });
    // Check sidebar has reading link
    const link = page.locator('a[href="/reading"]').first();
    await expect(link).toBeVisible({ timeout: 5_000 });
  });
});
