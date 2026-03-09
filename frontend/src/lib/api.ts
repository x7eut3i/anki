/**
 * API client for communicating with the FastAPI backend.
 */

import { getUserTimezone } from "./timezone";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface RequestOptions extends RequestInit {
  token?: string;
}

async function request<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, headers: extraHeaders, ...rest } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((extraHeaders as Record<string, string>) || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { headers, ...rest });

  if (!res.ok) {
    // Auto-logout on 401 (token expired)
    if (res.status === 401) {
      const { useAuthStore } = await import("@/lib/store");
      useAuthStore.getState().logout();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new APIError(res.status, body.detail || "Request failed");
  }

  if (res.status === 204) return null as T;
  return res.json();
}

export class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "APIError";
  }
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export const auth = {
  register: (data: { username: string; email: string; password: string }) =>
    request<LoginResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  login: (username: string, password: string) =>
    request<LoginResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  me: (token: string) =>
    request<any>("/api/auth/me", { token }),

  changePassword: (currentPassword: string, newPassword: string, token: string) =>
    request<any>("/api/auth/change-password", {
      method: "PUT",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      token,
    }),
};

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------

export const categories = {
  list: async (token: string) => {
    const data = await request<{ categories: any[]; ai_categories: any[] }>("/api/categories", { token });
    return data.categories;
  },
  listAll: async (token: string) => {
    const data = await request<{ categories: any[]; ai_categories: any[] }>("/api/categories", { token });
    return data;
  },
};

// ---------------------------------------------------------------------------
// Decks
// ---------------------------------------------------------------------------

export const decks = {
  list: async (token: string, search?: string) => {
    const params = search ? `?search=${encodeURIComponent(search)}` : "";
    const data = await request<{ decks: any[]; total: number }>(`/api/decks${params}`, { token });
    return data.decks;
  },

  get: (id: number, token: string) =>
    request<any>(`/api/decks/${id}`, { token }),

  create: (data: any, token: string) =>
    request<any>("/api/decks", { method: "POST", body: JSON.stringify(data), token }),

  update: (id: number, data: any, token: string) =>
    request<any>(`/api/decks/${id}`, { method: "PUT", body: JSON.stringify(data), token }),

  delete: (id: number, token: string) =>
    request<void>(`/api/decks/${id}`, { method: "DELETE", token }),

  batchDeleteCards: (cardIds: number[], token: string) =>
    request<{ deleted: number; total_requested: number }>("/api/decks/batch-delete-cards", {
      method: "POST",
      body: JSON.stringify({ card_ids: cardIds }),
      token,
    }),
};

// ---------------------------------------------------------------------------
// Cards
// ---------------------------------------------------------------------------

export const cards = {
  list: (params: Record<string, any>, token: string) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)])
    ).toString();
    return request<any>(`/api/cards?${qs}`, { token });
  },

  get: (id: number, token: string) =>
    request<any>(`/api/cards/${id}`, { token }),

  create: (data: any, token: string) =>
    request<any>("/api/cards", { method: "POST", body: JSON.stringify(data), token }),

  bulkCreate: (cardsList: any[], token: string) =>
    request<any>("/api/cards/bulk", { method: "POST", body: JSON.stringify({ cards: cardsList }), token }),

  update: (id: number, data: any, token: string) =>
    request<any>(`/api/cards/${id}`, { method: "PUT", body: JSON.stringify(data), token }),

  delete: (id: number, token: string) =>
    request<void>(`/api/cards/${id}`, { method: "DELETE", token }),

  batchApprove: (data: { card_ids?: number[]; deck_id?: number; all?: boolean }, token: string) =>
    request<{ approved: number; message: string }>("/api/cards/batch-approve", {
      method: "POST", body: JSON.stringify(data), token,
    }),

  regenerateQuestions: (id: number, token: string) =>
    request<{ questions: any[] }>(`/api/cards/${id}/regenerate-questions`, {
      method: "POST", token,
    }),
};

// ---------------------------------------------------------------------------
// Review
// ---------------------------------------------------------------------------

export const review = {
  getDue: (data: any, token: string) =>
    request<any>("/api/review/due", { method: "POST", body: JSON.stringify(data), token }),

  answer: (data: { card_id: number; rating: number; review_duration_ms?: number }, token: string) =>
    request<any>("/api/review/answer", { method: "POST", body: JSON.stringify(data), token }),

  batchAnswer: (data: { card_id: number; rating: number; review_duration_ms?: number }[], token: string, sessionId?: number | null) =>
    request<any>("/api/review/batch-answer", { method: "POST", body: JSON.stringify({ answers: data, session_id: sessionId || null }), token }),

  preview: (cardId: number, token: string) =>
    request<any>(`/api/review/preview/${cardId}`, { token }),

  batchPreview: (cardIds: number[], token: string) =>
    request<Record<string, any>>("/api/review/preview/batch", { method: "POST", body: JSON.stringify({ card_ids: cardIds }), token }),

  createSession: (data: any, token: string) =>
    request<any>("/api/review/session", { method: "POST", body: JSON.stringify(data), token }),

  getActiveSession: (token: string) =>
    request<any>("/api/review/session/active", { token }),

  getActiveQuizSession: (token: string) =>
    request<any>("/api/review/session/active?mode=quiz", { token }),

  updateProgress: (sessionId: number, cardId: number, isCorrect: boolean, token: string) =>
    request<any>(`/api/review/session/${sessionId}/progress`, {
      method: "POST",
      body: JSON.stringify({ card_id: cardId, is_correct: isCorrect }),
      token,
    }),

  stats: (token: string, tz?: string) =>
    request<any>(`/api/review/stats${tz ? `?tz=${encodeURIComponent(tz)}` : ''}`, { token }),

  resetAll: (token: string) =>
    request<any>("/api/review/reset/all", { method: "POST", token }),
};

// ---------------------------------------------------------------------------
// Quiz
// ---------------------------------------------------------------------------

export const quiz = {
  generate: (data: any, token: string) =>
    request<any>("/api/quiz/generate", { method: "POST", body: JSON.stringify(data), token }),

  submit: (sessionId: number, answers: any[], token: string) =>
    request<any>(`/api/quiz/submit/${sessionId}`, { method: "POST", body: JSON.stringify(answers), token }),

  save: (sessionId: number, data: { answers: Record<string, any>; current_q: number }, token: string) =>
    request<any>(`/api/quiz/save/${sessionId}`, { method: "POST", body: JSON.stringify(data), token }),
};

// ---------------------------------------------------------------------------
// AI
// ---------------------------------------------------------------------------

export const ai = {
  getConfig: (token: string) =>
    request<any>("/api/ai/config", { token }),

  saveConfig: (data: any, token: string) =>
    request<any>("/api/ai/config", { method: "PUT", body: JSON.stringify(data), token }),

  listConfigs: (token: string) =>
    request<any[]>("/api/ai/configs", { token }),

  createConfig: (data: any, token: string) =>
    request<any>("/api/ai/configs", { method: "POST", body: JSON.stringify(data), token }),

  activateConfig: (configId: number, token: string) =>
    request<any>(`/api/ai/configs/${configId}/activate`, { method: "POST", token }),

  renameConfig: (configId: number, name: string, token: string) =>
    request<any>(`/api/ai/configs/${configId}/rename`, { method: "PUT", body: JSON.stringify({ name }), token }),

  deleteConfig: (configId: number, token: string) =>
    request<void>(`/api/ai/configs/${configId}`, { method: "DELETE", token }),

  testConnection: (data: { api_base_url: string; api_key?: string; model: string }, token: string) => {
    // Only include api_key if user explicitly provided a new one
    const payload: any = { api_base_url: data.api_base_url, model: data.model };
    if (data.api_key) {
      payload.api_key = data.api_key;
    }
    return request<any>("/api/ai/test-connection", { method: "POST", body: JSON.stringify(payload), token });
  },

  listModels: (data: { api_base_url: string; api_key?: string }, token: string) => {
    const payload: any = { api_base_url: data.api_base_url, model: "" };
    if (data.api_key) {
      payload.api_key = data.api_key;
    }
    return request<{ success: boolean; models: string[]; error?: string }>("/api/ai/models", {
      method: "POST",
      body: JSON.stringify(payload),
      token,
    });
  },

  explain: (cardId: number, token: string) =>
    request<any>(`/api/ai/explain/${cardId}`, { method: "POST", token }),

  mnemonic: (cardId: number, token: string) =>
    request<any>(`/api/ai/mnemonic/${cardId}`, { method: "POST", token }),

  generate: (data: any, token: string) =>
    request<any>("/api/ai/generate", { method: "POST", body: JSON.stringify(data), token }),

  chat: (data: { message: string; card_id?: number; history?: { role: string; content: string }[] }, token: string) =>
    request<any>("/api/ai/chat", { method: "POST", body: JSON.stringify(data), token }),

  usage: (token: string) =>
    request<any>("/api/ai/usage", { token }),

  batchEnrich: (data: { card_ids?: number[]; deck_id?: number; batch_size?: number }, token: string) =>
    request<any>("/api/ai/batch-enrich", { method: "POST", body: JSON.stringify(data), token }),
  completeCards: (data: { cards: { front: string; category?: string }[]; deck_id: number }, token: string) =>
    request<{ cards: { front: string; back: string; explanation: string; distractors: string; meta_info?: string; tags?: string; category?: string }[]; completed: number }>("/api/ai/complete-cards", { method: "POST", body: JSON.stringify(data), token }),
  completeCardsAsync: (data: { cards: { front: string; category?: string }[]; deck_id: number; category_id?: number | null; allow_correction?: boolean }, token: string) =>
    request<{ job_id: number; message: string }>("/api/ai/complete-cards/async", { method: "POST", body: JSON.stringify(data), token }),
  smartImport: (deckId: number, file: File, token: string) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/api/ai/smart-import?deck_id=${deckId}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
  },
  smartImportAsync: (deckId: number, file: File, token: string) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/api/ai/smart-import/async?deck_id=${deckId}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
  },
  batchEnrichAsync: (data: { card_ids?: number[]; deck_id?: number; batch_size?: number }, token: string) =>
    request<any>("/api/ai/batch-enrich/async", { method: "POST", body: JSON.stringify(data), token }),

  fallbackStatus: (token: string) =>
    request<{ active: boolean; fallback_model?: string; reason?: string; remaining_seconds?: number }>("/api/ai/fallback-status", { token }),
};

// ---------------------------------------------------------------------------
// Import / Export
// ---------------------------------------------------------------------------

export const importExport = {
  importCSV: (deckId: number, file: File, token: string, categoryId?: number, allowCorrection?: boolean) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams({ deck_id: String(deckId) });
    if (categoryId) params.append("category_id", String(categoryId));
    if (allowCorrection) params.append("allow_correction", "true");
    return fetch(`${API_BASE}/api/import-export/import/csv?${params}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
  },

  importJSON: (deckId: number, file: File, token: string, categoryId?: number, allowCorrection?: boolean) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams({ deck_id: String(deckId) });
    if (categoryId) params.append("category_id", String(categoryId));
    if (allowCorrection) params.append("allow_correction", "true");
    return fetch(`${API_BASE}/api/import-export/import/json?${params}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
  },
  importExcel: (deckId: number, file: File, token: string, categoryId?: number, allowCorrection?: boolean) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams({ deck_id: String(deckId) });
    if (categoryId) params.append("category_id", String(categoryId));
    if (allowCorrection) params.append("allow_correction", "true");
    return fetch(`${API_BASE}/api/import-export/import/excel?${params}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
  },

  exportCSV: (deckId: number | undefined, token: string) => {
    const params = deckId != null ? `?deck_id=${deckId}` : "";
    return fetch(`${API_BASE}/api/import-export/export/csv${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  },

  exportJSON: (deckId: number | undefined, token: string) => {
    const params = deckId != null ? `?deck_id=${deckId}` : "";
    return fetch(`${API_BASE}/api/import-export/export/json${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  },

  importDirect: (deckId: number, file: File, token: string) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams({ deck_id: String(deckId) });
    return fetch(`${API_BASE}/api/import-export/import/direct?${params}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
  },
};

// ---------------------------------------------------------------------------
// Reading (Article Deep Reading / 文章精读)
// ---------------------------------------------------------------------------

export const reading = {
  list: (params: Record<string, any>, token: string) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)])
    ).toString();
    return request<any>(`/api/reading?${qs}`, { token });
  },

  get: (id: number, token: string) =>
    request<any>(`/api/reading/${id}`, { token }),

  dailyRecommendation: (token: string) =>
    request<any>("/api/reading/daily-recommendation", { token }),

  batchLookup: (sourceUrls: string[], token: string) =>
    request<Record<string, { id: number; title: string; quality_score: number; source_name: string }>>("/api/reading/batch-lookup", { method: "POST", body: JSON.stringify({ source_urls: sourceUrls }), token }),

  create: (data: { title: string; content: string; source_url?: string; source_name?: string; publish_date?: string; create_cards?: boolean }, token: string) =>
    request<any>("/api/reading", { method: "POST", body: JSON.stringify(data), token }),

  updateStatus: (id: number, status: string, token: string) =>
    request<any>(`/api/reading/${id}/status`, {
      method: "PUT",
      body: JSON.stringify({ status }),
      token,
    }),

  updateStar: (id: number, is_starred: boolean, token: string) =>
    request<any>(`/api/reading/${id}/star`, {
      method: "PUT",
      body: JSON.stringify({ is_starred }),
      token,
    }),

  delete: (id: number, token: string, deleteCards?: boolean) =>
    request<void>(`/api/reading/${id}${deleteCards ? '?delete_cards=true' : ''}`, { method: "DELETE", token }),

  createCard: (data: {
    selected_text: string;
    article_title: string;
    article_content?: string;
    source_url?: string;
    category_id?: number | null;
    preview?: boolean;
  }, token: string) =>
    request<any>("/api/reading/create-card", { method: "POST", body: JSON.stringify(data), token }),

  savePreviewCard: (data: {
    front: string;
    back: string;
    explanation?: string;
    distractors?: string[];
    tags?: string;
    category_id?: number | null;
    meta_info?: Record<string, any>;
    source_url?: string;
  }, token: string) =>
    request<any>("/api/reading/save-preview-card", { method: "POST", body: JSON.stringify(data), token }),

  fetchUrl: (url: string, token: string) =>
    request<any>("/api/reading/fetch-url", { method: "POST", body: JSON.stringify({ url }), token }),

  batchArchive: (days: number, token: string) =>
    request<any>(`/api/reading/batch-archive?days=${days}`, { method: "POST", token }),

  reanalyze: (id: number, token: string) =>
    request<any>(`/api/reading/${id}/reanalyze`, { method: "POST", token }),

  batchDelete: (ids: number[], token: string, deleteCards?: boolean) =>
    request<{ deleted: number }>("/api/reading/batch-delete", { method: "POST", body: JSON.stringify({ ids, delete_cards: deleteCards || false }), token }),

  batchReanalyze: (ids: number[], token: string) =>
    request<{ success: number; failed: number; total: number }>("/api/reading/batch-reanalyze", { method: "POST", body: JSON.stringify({ ids }), token }),

  repair: (token: string) =>
    request<{ message: string; total: number; need_reanalyze: number; need_cards_only: number; job_id: number | null }>("/api/reading/repair", { method: "POST", token }),

  // Article-linked cards
  getArticleCards: (analysisId: number, token: string) =>
    request<any>(`/api/reading/${analysisId}/cards`, { token }),

  deleteArticleCard: (analysisId: number, cardId: number, token: string) =>
    request<any>(`/api/reading/${analysisId}/cards/${cardId}`, { method: "DELETE", token }),

  // Import/Export articles
  exportArticles: (token: string) =>
    fetch(`${API_BASE}/api/reading/export/articles`, {
      headers: { Authorization: `Bearer ${token}` },
    }),

  importArticles: (file: File, token: string) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API_BASE}/api/reading/import/articles`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }).then((r) => r.json());
  },
};

// ---------------------------------------------------------------------------
// Sources (Article Source Management)
// ---------------------------------------------------------------------------

export const sources = {
  list: (token: string) =>
    request<any[]>("/api/sources", { token }),

  create: (data: { name: string; url: string; source_type?: string; category?: string; description?: string }, token: string) =>
    request<any>("/api/sources", { method: "POST", body: JSON.stringify(data), token }),

  update: (id: number, data: any, token: string) =>
    request<any>(`/api/sources/${id}`, { method: "PUT", body: JSON.stringify(data), token }),

  delete: (id: number, token: string) =>
    request<void>(`/api/sources/${id}`, { method: "DELETE", token }),

  test: (id: number, token: string) =>
    request<any>(`/api/sources/${id}/test`, { method: "POST", token }),

  testUrl: (data: { name: string; url: string; source_type?: string }, token: string) =>
    request<any>("/api/sources/test-url", { method: "POST", body: JSON.stringify(data), token }),

  resetDefaults: (token: string) =>
    request<any>("/api/sources/reset-defaults", { method: "POST", token }),

  backfill: (data: { start_date: string; end_date: string }, token: string) =>
    request<any>("/api/sources/rmrb-backfill", { method: "POST", body: JSON.stringify(data), token }),

  qiushiIssues: (year: number, token: string) =>
    request<{ year: number; issues: { issue: number; text: string; url: string }[] }>(`/api/sources/qiushi-issues?year=${year}`, { token }),

  qiushiBackfill: (data: { issues: { issue_url: string; issue_name: string }[] }, token: string) =>
    request<any>("/api/sources/qiushi-backfill", { method: "POST", body: JSON.stringify(data), token }),
};

// ---------------------------------------------------------------------------
// Prompts (Prompt Management)
// ---------------------------------------------------------------------------

export const prompts = {
  list: (token: string) =>
    request<any[]>("/api/prompts", { token }),

  get: (key: string, token: string) =>
    request<any>(`/api/prompts/${key}`, { token }),

  update: (key: string, data: { content?: string; model_override?: string }, token: string) =>
    request<any>(`/api/prompts/${key}`, { method: "PUT", body: JSON.stringify(data), token }),

  reset: (key: string, token: string) =>
    request<any>(`/api/prompts/${key}/reset`, { method: "POST", token }),
};

// ---------------------------------------------------------------------------
// Ingestion (Auto-fetch management)
// ---------------------------------------------------------------------------

export const ingestion = {
  getConfig: (token: string) =>
    request<any>("/api/ingestion/config", { token }),

  updateConfig: (data: any, token: string) =>
    request<any>("/api/ingestion/config", { method: "PUT", body: JSON.stringify(data), token }),

  run: (token: string) =>
    request<any>("/api/ingestion/run", { method: "POST", token }),

  cancel: (logId: number, token: string) =>
    request<any>(`/api/ingestion/cancel/${logId}`, { method: "POST", token }),

  getLogs: (limit?: number, token?: string) =>
    request<any[]>(`/api/ingestion/logs${limit ? `?limit=${limit}` : ""}`, { token: token || "" }),

  clearLogs: (token: string) =>
    request<any>("/api/ingestion/logs", { method: "DELETE", token }),
};

// ---------------------------------------------------------------------------
// Users (Admin user management)
// ---------------------------------------------------------------------------

export const users = {
  list: (token: string) =>
    request<any[]>("/api/users", { token }),

  create: (data: { username: string; email: string; password: string; is_admin?: boolean }, token: string) =>
    request<any>("/api/users", { method: "POST", body: JSON.stringify(data), token }),

  toggleActive: (userId: number, isActive: boolean, token: string) =>
    request<any>(`/api/users/${userId}/toggle-active`, {
      method: "PUT",
      body: JSON.stringify({ is_active: isActive }),
      token,
    }),

  resetPassword: (userId: number, newPassword: string, token: string) =>
    request<any>(`/api/users/${userId}/reset-password`, {
      method: "PUT",
      body: JSON.stringify({ new_password: newPassword }),
      token,
    }),

  delete: (userId: number, token: string) =>
    request<any>(`/api/users/${userId}`, {
      method: "DELETE",
      token,
    }),
};

// ---------------------------------------------------------------------------
// Logs (Log viewer)
// ---------------------------------------------------------------------------

export const logs = {
  listFiles: (token: string) =>
    request<any[]>("/api/logs", { token }),

  getEntries: (logType: string, params: {
    search?: string; level?: string; page?: number; page_size?: number; tail?: number; date?: string;
  }, token: string) => {
    const q = new URLSearchParams();
    if (params.search) q.set("search", params.search);
    if (params.level) q.set("level", params.level);
    if (params.page) q.set("page", String(params.page));
    if (params.page_size) q.set("page_size", String(params.page_size));
    if (params.tail) q.set("tail", String(params.tail));
    if (params.date) q.set("date", params.date);
    return request<any>(`/api/logs/${logType}?${q.toString()}`, { token });
  },

  getRaw: (logType: string, tail: number, token: string) =>
    request<any>(`/api/logs/${logType}/raw?tail=${tail}`, { token }),

  getAIStatistics: (token: string) =>
    request<any>("/api/logs/ai/statistics", { token }),

  getDates: (logType: string, token: string) =>
    request<string[]>(`/api/logs/${logType}/dates`, { token }),

  clear: (logType: string, token: string) =>
    request<any>(`/api/logs/${logType}`, { method: "DELETE", token }),

  getRetention: (token: string) =>
    request<{ retention_days: number }>("/api/logs/settings/retention", { token }),

  setRetention: (days: number, token: string) =>
    request<any>("/api/logs/settings/retention", {
      method: "PUT",
      body: JSON.stringify({ retention_days: days }),
      token,
    }),
};

// ---------------------------------------------------------------------------
// Statistics (comprehensive stats from DB)
// ---------------------------------------------------------------------------

export const stats = {
  ai: (days: number, token: string) =>
    request<any>(`/api/stats/ai?days=${days}&tz=${encodeURIComponent(getUserTimezone())}`, { token }),

  content: (days: number, token: string) =>
    request<any>(`/api/stats/content?days=${days}&tz=${encodeURIComponent(getUserTimezone())}`, { token }),

  study: (params: { days?: number; period?: string }, token: string) => {
    const q = new URLSearchParams();
    if (params.days) q.set("days", String(params.days));
    if (params.period) q.set("period", params.period);
    q.set("tz", getUserTimezone());
    return request<any>(`/api/stats/study?${q.toString()}`, { token });
  },
};

// ---------------------------------------------------------------------------
// Tags (Custom Tag Management)
// ---------------------------------------------------------------------------

export const tags = {
  list: (token: string) =>
    request<any[]>("/api/tags", { token }),

  detail: (tagId: number, token: string) =>
    request<any>(`/api/tags/${tagId}/detail`, { token }),

  create: (data: { name: string; color?: string }, token: string) =>
    request<any>("/api/tags", { method: "POST", body: JSON.stringify(data), token }),

  update: (id: number, data: { name?: string; color?: string }, token: string) =>
    request<any>(`/api/tags/${id}`, { method: "PUT", body: JSON.stringify(data), token }),

  delete: (id: number, token: string) =>
    request<void>(`/api/tags/${id}`, { method: "DELETE", token }),

  // Card tags
  getCardTags: (cardId: number, token: string) =>
    request<any[]>(`/api/tags/card/${cardId}`, { token }),

  addCardTag: (cardId: number, tagId: number, token: string) =>
    request<any>(`/api/tags/card/${cardId}/add/${tagId}`, { method: "POST", token }),

  removeCardTag: (cardId: number, tagId: number, token: string) =>
    request<any>(`/api/tags/card/${cardId}/remove/${tagId}`, { method: "DELETE", token }),

  // Article tags
  getArticleTags: (articleId: number, token: string) =>
    request<any[]>(`/api/tags/article/${articleId}`, { token }),

  addArticleTag: (articleId: number, tagId: number, token: string) =>
    request<any>(`/api/tags/article/${articleId}/add/${tagId}`, { method: "POST", token }),

  removeArticleTag: (articleId: number, tagId: number, token: string) =>
    request<any>(`/api/tags/article/${articleId}/remove/${tagId}`, { method: "DELETE", token }),
};

// ---------------------------------------------------------------------------
// AI Jobs (Async Job Tracking)
// ---------------------------------------------------------------------------

export const jobs = {
  list: (token: string, status?: string) => {
    const params = status ? `?status=${status}` : "";
    return request<any[]>(`/api/jobs${params}`, { token });
  },

  get: (jobId: number, token: string) =>
    request<any>(`/api/jobs/${jobId}`, { token }),

  delete: (jobId: number, token: string) =>
    request<void>(`/api/jobs/${jobId}`, { method: "DELETE", token }),

  clearCompleted: (token: string) =>
    request<any>("/api/jobs", { method: "DELETE", token }),
};

// ---------------------------------------------------------------------------
// Study Presets (Mixed Mode Custom Category Combos)
// ---------------------------------------------------------------------------

export const studyPresets = {
  list: async (token: string) => {
    const data = await request<{ presets: any[] }>("/api/study-presets", { token });
    return data.presets || [];
  },

  create: (data: { name: string; icon?: string; category_ids: number[]; deck_ids: number[]; card_count?: number }, token: string) =>
    request<any>("/api/study-presets", { method: "POST", body: JSON.stringify(data), token }),

  update: (id: number, data: { name?: string; icon?: string; category_ids?: number[]; deck_ids?: number[]; card_count?: number }, token: string) =>
    request<any>(`/api/study-presets/${id}`, { method: "PUT", body: JSON.stringify(data), token }),

  delete: (id: number, token: string) =>
    request<void>(`/api/study-presets/${id}`, { method: "DELETE", token }),
};
