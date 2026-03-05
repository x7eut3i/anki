/**
 * Tests for Quiz page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuizPage from "@/app/(app)/quiz/page";

// Mock API
vi.mock("@/lib/api", () => ({
  quiz: {
    generate: vi.fn(),
    submit: vi.fn(),
  },
  categories: {
    list: vi.fn(),
  },
}));

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({
    token: "test-token",
  }),
}));

import { quiz as quizApi, categories as catApi } from "@/lib/api";
const mockGenerate = quizApi.generate as ReturnType<typeof vi.fn>;
const mockSubmit = quizApi.submit as ReturnType<typeof vi.fn>;
const mockCatList = (catApi as any).list as ReturnType<typeof vi.fn>;

const sampleCats = [
  { id: 1, name: "法律", icon: "⚖️" },
  { id: 2, name: "政治", icon: "🏛️" },
];

const sampleQuestions = [
  {
    question_id: 1,
    card_id: 10,
    question_type: "choice",
    question: "下列哪项是正确的？",
    choices: ["选项A", "选项B", "选项C", "选项D"],
    category_name: "法律",
    time_limit: 60,
  },
  {
    question_id: 2,
    card_id: 20,
    question_type: "choice",
    question: "第二个问题是什么？",
    choices: ["甲", "乙", "丙", "丁"],
    category_name: "政治",
    time_limit: 60,
  },
];

describe("QuizPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCatList.mockResolvedValue(sampleCats);
    mockGenerate.mockResolvedValue({
      session_id: 42,
      questions: sampleQuestions,
    });
    mockSubmit.mockResolvedValue({ score: 1, total: 2 });
  });

  describe("Config screen", () => {
    it("should render config screen initially", async () => {
      render(<QuizPage />);
      expect(screen.getByText("模拟测试")).toBeInTheDocument();
      expect(screen.getByText("选择分类和题目数量开始测试")).toBeInTheDocument();
    });

    it("should display categories", async () => {
      render(<QuizPage />);
      await waitFor(() => {
        expect(screen.getByText(/法律/)).toBeInTheDocument();
      });
      expect(screen.getByText(/政治/)).toBeInTheDocument();
    });

    it("should show question count buttons", () => {
      render(<QuizPage />);
      expect(screen.getByText("10 题")).toBeInTheDocument();
      expect(screen.getByText("20 题")).toBeInTheDocument();
      expect(screen.getByText("50 题")).toBeInTheDocument();
      expect(screen.getByText("100 题")).toBeInTheDocument();
    });

    it("should have start button", () => {
      render(<QuizPage />);
      expect(screen.getByText("开始测试")).toBeInTheDocument();
    });

    it("should toggle category selection on click", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await waitFor(() => {
        expect(screen.getByText(/法律/)).toBeInTheDocument();
      });
      const catBadge = screen.getByText(/法律/);
      await user.click(catBadge);
      // Category should now be selected (badge variant changes)
      // Click again to deselect
      await user.click(catBadge);
    });
  });

  describe("Question screen", () => {
    it("should show questions after starting quiz", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("下列哪项是正确的？")).toBeInTheDocument();
      });
    });

    it("should show progress indicator", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText(/第 1 \/ 2 题/)).toBeInTheDocument();
      });
    });

    it("should show category badge on question", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("法律")).toBeInTheDocument();
      });
    });

    it("should display choice options", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("选项A")).toBeInTheDocument();
        expect(screen.getByText("选项B")).toBeInTheDocument();
        expect(screen.getByText("选项C")).toBeInTheDocument();
        expect(screen.getByText("选项D")).toBeInTheDocument();
      });
    });

    it("should navigate to next question", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("下列哪项是正确的？")).toBeInTheDocument();
      });

      // Click next button
      const nextBtn = screen.getByText("下一题");
      await user.click(nextBtn);

      expect(screen.getByText("第二个问题是什么？")).toBeInTheDocument();
      expect(screen.getByText(/第 2 \/ 2 题/)).toBeInTheDocument();
    });

    it("should select an answer", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("选项A")).toBeInTheDocument();
      });

      await user.click(screen.getByText("选项A"));
      // The button should have selected styles (we can check the class)
    });

    it("should call generate with card_count", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(mockGenerate).toHaveBeenCalledWith(
          expect.objectContaining({ card_count: 20 }),
          "test-token"
        );
      });
    });
  });

  describe("Result screen", () => {
    it("should show results after submission", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("选项A")).toBeInTheDocument();
      });

      // Select answers and submit
      await user.click(screen.getByText("选项A"));
      await user.click(screen.getByText("下一题"));
      await user.click(screen.getByText("甲"));
      await user.click(screen.getByText("提交答卷"));

      await waitFor(() => {
        expect(screen.getByText("1 / 2 题正确")).toBeInTheDocument();
      });
    });

    it("should submit with correct session_id", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("选项A")).toBeInTheDocument();
      });

      await user.click(screen.getByText("选项A"));
      await user.click(screen.getByText("下一题"));
      await user.click(screen.getByText("甲"));
      await user.click(screen.getByText("提交答卷"));

      await waitFor(() => {
        expect(mockSubmit).toHaveBeenCalledWith(
          42,
          expect.any(Array),
          "test-token"
        );
      });
    });

    it("should show reconfigure button on result", async () => {
      const user = userEvent.setup();
      render(<QuizPage />);
      await user.click(screen.getByText("开始测试"));

      await waitFor(() => {
        expect(screen.getByText("选项A")).toBeInTheDocument();
      });

      await user.click(screen.getByText("选项A"));
      await user.click(screen.getByText("下一题"));
      await user.click(screen.getByText("甲"));
      await user.click(screen.getByText("提交答卷"));

      await waitFor(() => {
        expect(screen.getByText("重新配置")).toBeInTheDocument();
        expect(screen.getByText("返回仪表盘")).toBeInTheDocument();
      });
    });
  });
});
