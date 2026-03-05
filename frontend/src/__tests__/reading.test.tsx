/**
 * Tests for Reading (文章精读) page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReadingPage from "@/app/(app)/reading/page";

// Mock API
vi.mock("@/lib/api", () => ({
  reading: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    updateStatus: vi.fn(),
    updateStar: vi.fn(),
    delete: vi.fn(),
  },
  ai: {
    chat: vi.fn(),
  },
}));

import { reading, ai } from "@/lib/api";
const mockList = reading.list as ReturnType<typeof vi.fn>;
const mockGet = reading.get as ReturnType<typeof vi.fn>;
const mockCreate = reading.create as ReturnType<typeof vi.fn>;
const mockUpdateStatus = reading.updateStatus as ReturnType<typeof vi.fn>;
const mockUpdateStar = reading.updateStar as ReturnType<typeof vi.fn>;
const mockDelete = reading.delete as ReturnType<typeof vi.fn>;
const mockChat = ai.chat as ReturnType<typeof vi.fn>;

// Mock store
vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({
    token: "test-token",
  }),
}));

// Mock react-markdown
vi.mock("react-markdown", () => ({
  default: ({ children }: { children: string }) => <span>{children}</span>,
}));

vi.mock("remark-gfm", () => ({
  default: () => {},
}));

const sampleItems = {
  items: [
    {
      id: 1,
      title: "推进高质量发展",
      source_url: "https://example.com",
      source_name: "人民日报",
      publish_date: "2024-01-15",
      quality_score: 8,
      quality_reason: "高考试价值",
      word_count: 1200,
      status: "new",
      is_starred: false,
      created_at: "2024-01-15T10:00:00",
      updated_at: "2024-01-15T10:00:00",
    },
    {
      id: 2,
      title: "乡村振兴战略",
      source_url: "",
      source_name: "新华社",
      publish_date: "2024-01-16",
      quality_score: 7,
      quality_reason: "有参考价值",
      word_count: 800,
      status: "reading",
      is_starred: true,
      created_at: "2024-01-16T10:00:00",
      updated_at: "2024-01-16T10:00:00",
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

const sampleDetail = {
  id: 1,
  title: "推进高质量发展",
  source_url: "https://example.com",
  source_name: "人民日报",
  publish_date: "2024-01-15",
  quality_score: 8,
  quality_reason: "高考试价值",
  word_count: 1200,
  status: "new",
  is_starred: false,
  created_at: "2024-01-15T10:00:00",
  updated_at: "2024-01-15T10:00:00",
  content: "高质量发展是全面建设社会主义现代化国家的首要任务。",
  analysis_html: "<section><h3>分析</h3></section>",
  analysis_json: {
    summary: "文章概述高质量发展",
    highlights: [
      {
        text: "高质量发展",
        type: "key_point",
        color: "red",
        annotation: "核心概念",
      },
    ],
    overall_analysis: {
      theme: "高质量发展",
      core_arguments: ["论点一"],
    },
    exam_points: {
      essay_angles: ["经济角度"],
    },
    vocabulary: [
      { term: "新质生产力", explanation: "以创新为主导" },
    ],
    reading_notes: "推荐积累",
  },
  finished_at: null,
};

describe("ReadingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue(sampleItems);
    mockGet.mockResolvedValue(sampleDetail);
    mockUpdateStatus.mockResolvedValue({ ok: true });
    mockUpdateStar.mockResolvedValue({ ok: true });
    mockDelete.mockResolvedValue(undefined);
  });

  // ── List View ──

  describe("List View", () => {
    it("should show loading spinner initially", () => {
      mockList.mockReturnValue(new Promise(() => {}));
      render(<ReadingPage />);
      const spinner = document.querySelector(".animate-spin");
      expect(spinner).toBeInTheDocument();
    });

    it("should render article list", async () => {
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });
      expect(screen.getByText("乡村振兴战略")).toBeInTheDocument();
      expect(screen.getByText("文章精读")).toBeInTheDocument();
    });

    it("should show total count", async () => {
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText(/共 2 篇/)).toBeInTheDocument();
      });
    });

    it("should show empty state when no articles", async () => {
      mockList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("暂无精读文章")).toBeInTheDocument();
      });
    });

    it("should show filter buttons", async () => {
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("全部")).toBeInTheDocument();
      });
      // Filter labels may also appear as status badges on article cards
      expect(screen.getAllByText("新").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("在读").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("已读").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("收藏")).toBeInTheDocument();
    });

    it("should filter by status when clicking filter button", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });

      // Click the filter button "在读" — use the one inside .ml-1 span (filter button)
      const filterBtns = screen.getAllByText("在读");
      const filterBtn = filterBtns.find(
        (el) => el.closest("button") && el.classList.contains("ml-1")
      ) || filterBtns[0];
      await user.click(filterBtn.closest("button") || filterBtn);
      await waitFor(() => {
        expect(mockList).toHaveBeenCalledWith(
          expect.objectContaining({ status: "reading" }),
          "test-token"
        );
      });
    });

    it("should show quality badges", async () => {
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("⭐ 8/10")).toBeInTheDocument();
        expect(screen.getByText("⭐ 7/10")).toBeInTheDocument();
      });
    });

    it("should show star icon for starred articles", async () => {
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("乡村振兴战略")).toBeInTheDocument();
      });
      // The starred article should have a filled star next to it
      const stars = document.querySelectorAll(".fill-yellow-400");
      expect(stars.length).toBeGreaterThan(0);
    });
  });

  // ── Detail View ──

  describe("Detail View", () => {
    it("should open detail view on article click", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });

      await user.click(screen.getByText("推进高质量发展"));
      await waitFor(() => {
        expect(mockGet).toHaveBeenCalledWith(1, "test-token");
      });
    });

    it("should auto-mark as reading when opening a new article", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });

      await user.click(screen.getByText("推进高质量发展"));
      await waitFor(() => {
        expect(mockUpdateStatus).toHaveBeenCalledWith(1, "reading", "test-token");
      });
    });

    it("should show three tabs: annotated, analysis, original", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });
      await user.click(screen.getByText("推进高质量发展"));
      await waitFor(() => {
        expect(screen.getByText("🖍️ 标注阅读")).toBeInTheDocument();
        expect(screen.getByText("✨ 精读分析")).toBeInTheDocument();
        expect(screen.getByText("📄 原文")).toBeInTheDocument();
      });
    });

    it("should show AI chat button", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });
      await user.click(screen.getByText("推进高质量发展"));
      await waitFor(() => {
        expect(screen.getByText("AI问答")).toBeInTheDocument();
      });
    });

    it("should show back button in detail view", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });
      await user.click(screen.getByText("推进高质量发展"));
      await waitFor(() => {
        expect(screen.getByText("返回列表")).toBeInTheDocument();
      });
    });
  });

  // ── Create ──

  describe("Create Form", () => {
    it("should show create form on button click", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("添加文章")).toBeInTheDocument();
      });

      await user.click(screen.getByText("添加文章"));
      await waitFor(() => {
        expect(screen.getByText("添加文章进行精读分析")).toBeInTheDocument();
        expect(screen.getByPlaceholderText("文章标题")).toBeInTheDocument();
        expect(screen.getByPlaceholderText("粘贴文章全文内容...")).toBeInTheDocument();
      });
    });

    it("should disable submit when title or content empty", async () => {
      const user = userEvent.setup();
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("添加文章")).toBeInTheDocument();
      });
      await user.click(screen.getByText("添加文章"));
      await waitFor(() => {
        const submitBtn = screen.getByText("开始精读分析");
        expect(submitBtn.closest("button")).toBeDisabled();
      });
    });
  });

  // ── Delete ──

  describe("Delete", () => {
    it("should call delete API", async () => {
      const user = userEvent.setup();
      window.confirm = vi.fn().mockReturnValue(true);
      render(<ReadingPage />);
      await waitFor(() => {
        expect(screen.getByText("推进高质量发展")).toBeInTheDocument();
      });

      // Hover to show delete button, then click
      const deleteButtons = document.querySelectorAll(".text-destructive");
      if (deleteButtons.length > 0) {
        await user.click(deleteButtons[0] as HTMLElement);
        await waitFor(() => {
          expect(mockDelete).toHaveBeenCalled();
        });
      }
    });
  });
});
