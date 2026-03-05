/**
 * Tests for AI page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AIPage from "@/app/(app)/ai/page";

vi.mock("@/lib/api", () => ({
  ai: {
    getConfig: vi.fn(),
    saveConfig: vi.fn(),
    testConnection: vi.fn(),
    listModels: vi.fn(),
    chat: vi.fn(),
  },
}));

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({ token: "test-token" }),
}));

import { ai } from "@/lib/api";
const mockGetConfig = ai.getConfig as ReturnType<typeof vi.fn>;
const mockSaveConfig = ai.saveConfig as ReturnType<typeof vi.fn>;
const mockTestConnection = ai.testConnection as ReturnType<typeof vi.fn>;
const mockListModels = ai.listModels as ReturnType<typeof vi.fn>;
const mockChat = ai.chat as ReturnType<typeof vi.fn>;

describe("AIPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetConfig.mockResolvedValue({
      api_base_url: "https://api.deepseek.com/v1",
      model: "deepseek-chat",
      max_daily_calls: 100,
    });
    mockSaveConfig.mockResolvedValue({ success: true });
    mockTestConnection.mockResolvedValue({ success: true });
    mockListModels.mockResolvedValue({
      success: true,
      models: ["deepseek-chat", "deepseek-coder"],
    });
    mockChat.mockResolvedValue({ response: "AI回复" });
  });

  describe("Config tab", () => {
    it("should render page title", () => {
      render(<AIPage />);
      expect(screen.getByText("AI 助手")).toBeInTheDocument();
    });

    it("should render config and chat tabs", () => {
      render(<AIPage />);
      expect(screen.getByText("配置")).toBeInTheDocument();
      expect(screen.getByText("AI 对话")).toBeInTheDocument();
    });

    it("should show config tab by default", () => {
      render(<AIPage />);
      expect(screen.getByText("AI 服务配置")).toBeInTheDocument();
    });

    it("should load config on mount", async () => {
      render(<AIPage />);
      await waitFor(() => {
        expect(mockGetConfig).toHaveBeenCalledWith("test-token");
      });
    });

    it("should display API endpoint input", () => {
      render(<AIPage />);
      expect(screen.getByPlaceholderText("https://api.deepseek.com/v1")).toBeInTheDocument();
    });

    it("should display API key input", () => {
      render(<AIPage />);
      expect(screen.getByPlaceholderText("sk-...")).toBeInTheDocument();
    });

    it("should have save button", () => {
      render(<AIPage />);
      expect(screen.getByText("保存配置")).toBeInTheDocument();
    });

    it("should have test connection button", () => {
      render(<AIPage />);
      expect(screen.getByText("测试连接")).toBeInTheDocument();
    });

    it("should have fetch models button", () => {
      render(<AIPage />);
      expect(screen.getByText("拉取模型")).toBeInTheDocument();
    });

    it("should show daily call limit input", () => {
      render(<AIPage />);
      expect(screen.getByText("每日调用限制")).toBeInTheDocument();
    });

    it("should save config on button click", async () => {
      const user = userEvent.setup();
      render(<AIPage />);
      await waitFor(() => {
        expect(mockGetConfig).toHaveBeenCalled();
      });

      await user.click(screen.getByText("保存配置"));

      await waitFor(() => {
        expect(mockSaveConfig).toHaveBeenCalledWith(
          expect.objectContaining({ api_base_url: expect.any(String) }),
          "test-token"
        );
      });
    });

    it("should test connection and show success", async () => {
      const user = userEvent.setup();
      render(<AIPage />);

      // Fill in required fields
      const keyInput = screen.getByPlaceholderText("sk-...");
      await user.type(keyInput, "sk-test-key");

      await waitFor(() => {
        expect(mockGetConfig).toHaveBeenCalled();
      });

      await user.click(screen.getByText("测试连接"));

      await waitFor(() => {
        expect(screen.getByText("连接成功")).toBeInTheDocument();
      });
    });

    it("should show connection failure message", async () => {
      mockTestConnection.mockRejectedValue(new Error("Failed"));
      const user = userEvent.setup();
      render(<AIPage />);

      const keyInput = screen.getByPlaceholderText("sk-...");
      await user.type(keyInput, "sk-bad-key");

      await waitFor(() => {
        expect(mockGetConfig).toHaveBeenCalled();
      });

      await user.click(screen.getByText("测试连接"));

      await waitFor(() => {
        expect(screen.getByText("连接失败，请检查配置")).toBeInTheDocument();
      });
    });

    it("should show supported AI services", () => {
      render(<AIPage />);
      expect(screen.getByText("支持的 AI 服务：")).toBeInTheDocument();
      expect(screen.getByText(/DeepSeek/)).toBeInTheDocument();
      expect(screen.getAllByText(/OpenAI/).length).toBeGreaterThanOrEqual(1);
    });

    it("should fetch and display model list", async () => {
      const user = userEvent.setup();
      render(<AIPage />);

      const keyInput = screen.getByPlaceholderText("sk-...");
      await user.type(keyInput, "sk-test");

      await waitFor(() => {
        expect(mockGetConfig).toHaveBeenCalled();
      });

      await user.click(screen.getByText("拉取模型"));

      await waitFor(() => {
        expect(mockListModels).toHaveBeenCalled();
      });
    });
  });

  describe("Chat tab", () => {
    it("should switch to chat tab", async () => {
      const user = userEvent.setup();
      render(<AIPage />);
      await user.click(screen.getByText("AI 对话"));
      expect(screen.getByText("向 AI 助手提问学习相关问题")).toBeInTheDocument();
    });

    it("should show suggestion badges", async () => {
      const user = userEvent.setup();
      render(<AIPage />);
      await user.click(screen.getByText("AI 对话"));
      expect(screen.getByText("什么是行政法的基本原则？")).toBeInTheDocument();
    });

    it("should send message and display response", async () => {
      const user = userEvent.setup();
      render(<AIPage />);
      await user.click(screen.getByText("AI 对话"));

      const chatInput = screen.getByPlaceholderText("输入你的问题...");
      await user.type(chatInput, "你好");

      // Find the send button
      const sendButtons = screen.getAllByRole("button");
      const sendBtn = sendButtons.find(
        (btn) => btn.querySelector("svg") !== null && !btn.textContent
      );

      // Click last button (send)
      if (sendBtn) {
        await user.click(sendBtn);
      }

      await waitFor(() => {
        // User message should appear
        expect(screen.getByText("你好")).toBeInTheDocument();
      });
    });

    it("should show AI error response on failure", async () => {
      mockChat.mockRejectedValue(new Error("AI error"));
      const user = userEvent.setup();
      render(<AIPage />);
      await user.click(screen.getByText("AI 对话"));

      const chatInput = screen.getByPlaceholderText("输入你的问题...");
      await user.type(chatInput, "测试");

      // Submit via Enter
      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(screen.getByText(/AI 回复失败/)).toBeInTheDocument();
      });
    });
  });
});
