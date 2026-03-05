/**
 * E2E test helpers: start a fresh backend, import content, manage users.
 *
 * The test environment uses a TEMPORARY database so the production
 * database is never touched.
 */
import { test as base, expect, type Page } from "@playwright/test";
import { execSync, spawn, type ChildProcess } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

const ROOT = path.resolve(__dirname, "../..");
const BACKEND = path.join(ROOT, "backend");
const CONTENT = path.join(ROOT, "content");
const VENV_PYTHON = path.join(BACKEND, ".venv", "Scripts", "python.exe");
const IMPORT_SCRIPT = path.join(CONTENT, "import_content.py");

// Test user credentials
export const TEST_USER = {
  username: "testuser",
  email: "test@example.com",
  password: "test123456",
};

// AI config from ai_config.json
const AI_CONFIG_PATH = path.join(ROOT, "ai_config.json");

export function loadAIConfig() {
  try {
    const raw = fs.readFileSync(AI_CONFIG_PATH, "utf-8");
    const cfg = JSON.parse(raw);
    return {
      api_base_url: cfg.api_base_url || "",
      api_key: cfg.api_key || "",
      model: cfg.model || "",
      max_daily_calls: cfg.max_daily_calls || 100,
    };
  } catch {
    return null;
  }
}

let serverProcess: ChildProcess | null = null;
let testDbPath: string = "";

/**
 * Start a fresh backend with a temporary database.
 */
export async function startTestServer(): Promise<string> {
  // Create temp DB path
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "anki-e2e-"));
  testDbPath = path.join(tmpDir, "test.db");

  const env = {
    ...process.env,
    DATABASE_URL: `sqlite:///${testDbPath}`,
    SECRET_KEY: "e2e-test-secret-key-12345",
  };

  // Create test user via manage_users.py
  execSync(
    `"${VENV_PYTHON}" manage_users.py add ${TEST_USER.username} ${TEST_USER.email} ${TEST_USER.password} --admin`,
    { cwd: BACKEND, env, stdio: "pipe" }
  );

  // Import content
  execSync(
    `"${VENV_PYTHON}" "${IMPORT_SCRIPT}" --db "${testDbPath}"`,
    { cwd: CONTENT, env, stdio: "pipe" }
  );

  // Start uvicorn
  serverProcess = spawn(
    VENV_PYTHON,
    ["-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    { cwd: BACKEND, env, stdio: "pipe" }
  );

  // Wait for server to be ready
  const startTime = Date.now();
  while (Date.now() - startTime < 15_000) {
    try {
      const res = await fetch("http://localhost:8000/api/health");
      if (res.ok) return testDbPath;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("Server failed to start within 15 seconds");
}

export async function stopTestServer() {
  if (serverProcess) {
    serverProcess.kill("SIGTERM");
    serverProcess = null;
  }
  // Clean up temp DB
  if (testDbPath && fs.existsSync(testDbPath)) {
    try {
      fs.unlinkSync(testDbPath);
      fs.rmdirSync(path.dirname(testDbPath));
    } catch {
      // ignore cleanup errors
    }
  }
}

/**
 * Login helper — fills form and submits.
 */
export async function loginAs(
  page: Page,
  username: string = TEST_USER.username,
  password: string = TEST_USER.password
) {
  await page.goto("/login");
  await page.fill('input[placeholder="请输入用户名"]', username);
  await page.fill('input[placeholder="请输入密码"]', password);
  await page.click('button[type="submit"]');
  // Wait for redirect to dashboard
  await page.waitForURL("**/dashboard", { timeout: 10_000 });
}
