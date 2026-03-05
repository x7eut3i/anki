/**
 * Tests for the API client module
 */
import { describe, it, expect, beforeEach, vi, type Mock } from "vitest";
import { auth, categories, decks, cards, review, quiz, ai, importExport, APIError } from "@/lib/api";

// Mock global fetch
const mockFetch = vi.fn() as Mock;
global.fetch = mockFetch;

function mockResponse(data: any, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
    blob: () => Promise.resolve(new Blob()),
    statusText: "OK",
  };
}

function mockErrorResponse(detail: string, status = 400) {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
    statusText: "Bad Request",
  };
}

describe("APIError", () => {
  it("should have correct properties", () => {
    const err = new APIError(404, "Not found");
    expect(err.status).toBe(404);
    expect(err.message).toBe("Not found");
    expect(err.name).toBe("APIError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("auth API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("login should POST credentials", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ access_token: "tok123", token_type: "bearer" })
    );
    const result = await auth.login("admin", "pass123");
    expect(result.access_token).toBe("tok123");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ username: "admin", password: "pass123" }),
      })
    );
  });

  it("register should POST user data", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ access_token: "tok456", token_type: "bearer" })
    );
    const result = await auth.register({
      username: "new_user",
      email: "test@example.com",
      password: "password",
    });
    expect(result.access_token).toBe("tok456");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.username).toBe("new_user");
    expect(body.email).toBe("test@example.com");
  });

  it("me should GET with auth header", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ id: 1, username: "admin", email: "a@b.com" })
    );
    const result = await auth.me("my-token");
    expect(result.username).toBe("admin");
    const headers = mockFetch.mock.calls[0][1].headers;
    expect(headers["Authorization"]).toBe("Bearer my-token");
  });

  it("login should throw APIError on failure", async () => {
    mockFetch.mockResolvedValueOnce(mockErrorResponse("Invalid credentials", 401));
    await expect(auth.login("bad", "bad")).rejects.toThrow("Invalid credentials");
  });
});

describe("categories API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("list should return categories array", async () => {
    const cats = [
      { id: 1, name: "法律", icon: "⚖️" },
      { id: 2, name: "政治", icon: "🏛️" },
    ];
    mockFetch.mockResolvedValueOnce(mockResponse({ categories: cats }));
    const result = await categories.list("token");
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe("法律");
  });
});

describe("decks API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("list should return decks", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ decks: [{ id: 1, name: "Deck1" }], total: 1 })
    );
    const result = await decks.list("token");
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Deck1");
  });

  it("get should fetch single deck", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ id: 5, name: "Test Deck" })
    );
    const result = await decks.get(5, "token");
    expect(result.id).toBe(5);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/decks/5",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer token" }) })
    );
  });

  it("create should POST deck data", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ id: 10, name: "New Deck" })
    );
    await decks.create({ name: "New Deck" }, "token");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
  });

  it("delete should send DELETE request", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, status: 204, json: () => Promise.resolve(null), statusText: "No Content" });
    await decks.delete(3, "token");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/decks/3",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("update should send PUT request", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ id: 2, name: "Updated" }));
    await decks.update(2, { name: "Updated" }, "token");
    expect(mockFetch.mock.calls[0][1].method).toBe("PUT");
  });
});

describe("cards API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("list should build query params", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ cards: [], total: 0 })
    );
    await cards.list({ deck_id: 5, page: 1, page_size: 20 }, "token");
    expect(mockFetch.mock.calls[0][0]).toContain("deck_id=5");
    expect(mockFetch.mock.calls[0][0]).toContain("page=1");
    expect(mockFetch.mock.calls[0][0]).toContain("page_size=20");
  });

  it("list should filter out null params", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ cards: [] }));
    await cards.list({ deck_id: 1, category_id: null }, "token");
    expect(mockFetch.mock.calls[0][0]).not.toContain("category_id");
  });

  it("create should POST card data", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ id: 1 }));
    await cards.create({ front: "Q", back: "A" }, "token");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
    expect(mockFetch.mock.calls[0][0]).toBe("/api/cards");
  });

  it("bulkCreate should POST to /api/cards/bulk", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ created: 3 }));
    await cards.bulkCreate([{ front: "Q1" }, { front: "Q2" }], "token");
    expect(mockFetch.mock.calls[0][0]).toBe("/api/cards/bulk");
  });
});

describe("review API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("getDue should POST with body", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ cards: [{ id: 1 }], total: 1 })
    );
    await review.getDue({ limit: 20 }, "token");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
    expect(mockFetch.mock.calls[0][0]).toBe("/api/review/due");
  });

  it("answer should POST rating", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ success: true }));
    await review.answer({ card_id: 1, rating: 3 }, "token");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.card_id).toBe(1);
    expect(body.rating).toBe(3);
  });

  it("preview should GET card preview", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ "1": "1m", "2": "10m", "3": "1d", "4": "4d" })
    );
    const result = await review.preview(42, "token");
    expect(result["3"]).toBe("1d");
    expect(mockFetch.mock.calls[0][0]).toBe("/api/review/preview/42");
  });

  it("stats should GET review statistics", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ total_cards: 100, today_reviews: 20 })
    );
    const result = await review.stats("token");
    expect(result.total_cards).toBe(100);
  });
});

describe("quiz API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("generate should POST quiz config", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        session_id: 1,
        questions: [{ question_id: 1, question: "Q?" }],
      })
    );
    const result = await quiz.generate(
      { category_ids: [1, 2], card_count: 10 },
      "token"
    );
    expect(result.session_id).toBe(1);
    expect(result.questions).toHaveLength(1);
  });

  it("submit should POST to /api/quiz/submit/{sessionId}", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ score: 8, total: 10 })
    );
    const answers = [
      { question_id: 1, card_id: 10, answer: "A" },
      { question_id: 2, card_id: 20, answer: "B" },
    ];
    const result = await quiz.submit(42, answers, "token");
    expect(result.score).toBe(8);
    expect(mockFetch.mock.calls[0][0]).toBe("/api/quiz/submit/42");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
  });
});

describe("ai API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("getConfig should GET ai config", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ api_base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" })
    );
    const result = await ai.getConfig("token");
    expect(result.api_base_url).toBe("https://api.deepseek.com/v1");
  });

  it("saveConfig should PUT config data", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ success: true }));
    await ai.saveConfig(
      { api_base_url: "https://api.openai.com/v1", model: "gpt-4o" },
      "token"
    );
    expect(mockFetch.mock.calls[0][1].method).toBe("PUT");
    expect(mockFetch.mock.calls[0][0]).toBe("/api/ai/config");
  });

  it("testConnection should POST connection test", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ success: true }));
    const result = await ai.testConnection(
      { api_base_url: "https://api.deepseek.com/v1", api_key: "sk-xxx", model: "deepseek-chat" },
      "token"
    );
    expect(result.success).toBe(true);
    expect(mockFetch.mock.calls[0][0]).toBe("/api/ai/test-connection");
  });

  it("listModels should POST and return model list", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ success: true, models: ["model-a", "model-b"] })
    );
    const result = await ai.listModels(
      { api_base_url: "https://api.deepseek.com/v1", api_key: "sk-xxx" },
      "token"
    );
    expect(result.success).toBe(true);
    expect(result.models).toEqual(["model-a", "model-b"]);
    // Should include model: "" in body
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.model).toBe("");
  });

  it("chat should POST message", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ response: "AI回复内容" })
    );
    const result = await ai.chat({ message: "你好", context: "学习" }, "token");
    expect(result.response).toBe("AI回复内容");
  });

  it("explain should POST to /api/ai/explain/{cardId}", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ explanation: "解释内容" })
    );
    await ai.explain(7, "token");
    expect(mockFetch.mock.calls[0][0]).toBe("/api/ai/explain/7");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
  });
});

describe("importExport API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("importCSV should POST FormData", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ imported: 5 }));
    const file = new File(["content"], "test.csv", { type: "text/csv" });
    const result = await importExport.importCSV(1, file, "token");
    expect(result.imported).toBe(5);
    expect(mockFetch.mock.calls[0][0]).toContain("/api/import-export/import/csv");
    expect(mockFetch.mock.calls[0][0]).toContain("deck_id=1");
  });

  it("importJSON should POST FormData", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ imported: 10 }));
    const file = new File(["{}"], "test.json", { type: "application/json" });
    const result = await importExport.importJSON(2, file, "token");
    expect(result.imported).toBe(10);
  });

  it("exportCSV should GET with deck_id", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      blob: () => Promise.resolve(new Blob(["csv-data"])),
    });
    await importExport.exportCSV(3, "token");
    expect(mockFetch.mock.calls[0][0]).toContain("/api/import-export/export/csv");
    expect(mockFetch.mock.calls[0][0]).toContain("deck_id=3");
  });

  it("importExcel should POST FormData", async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ created: 3, errors: [] }));
    const file = new File(["xlsx-data"], "test.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const result = await importExport.importExcel(4, file, "token");
    expect(result.created).toBe(3);
    expect(mockFetch.mock.calls[0][0]).toContain("/api/import-export/import/excel");
    expect(mockFetch.mock.calls[0][0]).toContain("deck_id=4");
  });
});

describe("review session API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("createSession should POST session data", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ id: 1, total_cards: 10, mode: "review" })
    );
    const result = await review.createSession(
      { mode: "review", card_limit: 50 },
      "token"
    );
    expect(result.id).toBe(1);
    expect(result.total_cards).toBe(10);
    expect(mockFetch.mock.calls[0][0]).toBe("/api/review/session");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
  });

  it("getActiveSession should GET active session", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ id: 5, mode: "review", is_completed: false })
    );
    const result = await review.getActiveSession("token");
    expect(result.id).toBe(5);
    expect(mockFetch.mock.calls[0][0]).toBe("/api/review/session/active");
  });

  it("updateProgress should POST progress data", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ cards_reviewed: 3, cards_correct: 2 })
    );
    const result = await review.updateProgress(1, 42, true, "token");
    expect(result.cards_reviewed).toBe(3);
    expect(mockFetch.mock.calls[0][0]).toBe("/api/review/session/1/progress");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.card_id).toBe(42);
    expect(body.is_correct).toBe(true);
  });
});

describe("ai smart import API", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("smartImport should POST file to /api/ai/smart-import", async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ created: 5, message: "导入成功" })
    );
    const file = new File(["content"], "test.txt", { type: "text/plain" });
    const result = await ai.smartImport(1, file, "token");
    expect(result.created).toBe(5);
    expect(mockFetch.mock.calls[0][0]).toContain("/api/ai/smart-import");
    expect(mockFetch.mock.calls[0][0]).toContain("deck_id=1");
  });
});
