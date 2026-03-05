/**
 * Tests for Flashcard component
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Flashcard from "@/components/flashcard";

// Q&A card (no distractors)
const qaCard = {
  id: 1,
  front: "什么是法律？",
  back: "法律是由国家制定的行为规范",
  explanation: "法律是由国家立法机关制定，由国家强制力保证实施的行为规范。",
  distractors: "",
  category_name: "法律基础",
};

// Choice card (has distractors)
const choiceCard = {
  id: 2,
  front: "行政法的基本原则不包括？",
  back: "随意性原则",
  explanation: "行政法的基本原则包括合法性原则、合理性原则和程序正当原则，不包括随意性原则。",
  distractors: JSON.stringify(["合法性原则", "合理性原则", "程序正当原则"]),
  category_name: "行政法",
};

// Card with meta_info
const metaCard = {
  id: 3,
  front: "我国的根本政治制度是什么？",
  back: "人民代表大会制度",
  explanation: "人民代表大会制度是我国的根本政治制度。",
  distractors: "",
  meta_info: JSON.stringify({
    knowledge_type: "politics",
    subject: "根本政治制度",
    knowledge: {
      key_points: ["根本政治制度", "人民当家作主"],
      related: ["政治协商制度", "民族区域自治制度"],
      memory_tips: "根本=人大",
    },
    exam_focus: {
      xingce_relevant: true,
      shenlun_relevant: false,
      difficulty: "easy",
      frequency: "high",
    },
  }),
  category_name: "政治理论",
};

describe("Flashcard", () => {
  const mockToggle = vi.fn();
  const mockRate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Q&A card", () => {
    it("should render front text", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      expect(screen.getByText("什么是法律？")).toBeInTheDocument();
    });

    it("should show card type badge as 问答题", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("问答题")).toBeInTheDocument();
    });

    it("should show category badge", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("法律基础")).toBeInTheDocument();
    });

    it("should show hint text when answer is hidden", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("点击或按空格显示答案")).toBeInTheDocument();
    });

    it("should not show hint when answer is visible", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.queryByText("点击或按空格显示答案")).not.toBeInTheDocument();
    });

    it("should show answer text when showAnswer is true", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("法律是由国家制定的行为规范")).toBeInTheDocument();
    });

    it("should show explanation when showAnswer is true", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText(/国家立法机关制定/)).toBeInTheDocument();
    });

    it("should call onToggleAnswer when card is clicked", async () => {
      const user = userEvent.setup();
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      await user.click(screen.getByText("什么是法律？"));
      expect(mockToggle).toHaveBeenCalled();
    });

    it("should show rating buttons when answer is shown", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      expect(screen.getByText("忘了")).toBeInTheDocument();
      expect(screen.getByText("困难")).toBeInTheDocument();
      expect(screen.getByText("记得")).toBeInTheDocument();
      expect(screen.getByText("简单")).toBeInTheDocument();
    });

    it("should not show rating buttons when answer is hidden", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      expect(screen.queryByText("忘了")).not.toBeInTheDocument();
    });

    it("should call onRate with correct value", async () => {
      const user = userEvent.setup();
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      await user.click(screen.getByText("记得"));
      expect(mockRate).toHaveBeenCalledWith(3);
    });

    it("should call onRate(1) when clicking 忘了", async () => {
      const user = userEvent.setup();
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      await user.click(screen.getByText("忘了"));
      expect(mockRate).toHaveBeenCalledWith(1);
    });

    it("should call onRate(4) when clicking 简单", async () => {
      const user = userEvent.setup();
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      await user.click(screen.getByText("简单"));
      expect(mockRate).toHaveBeenCalledWith(4);
    });

    it("should not show ratings when showRatings is false", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
          showRatings={false}
        />
      );
      expect(screen.queryByText("忘了")).not.toBeInTheDocument();
    });
  });

  describe("Choice card", () => {
    it("should render choices with correct answer and distractors", () => {
      render(
        <Flashcard
          card={choiceCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("随意性原则")).toBeInTheDocument();
      expect(screen.getByText("合法性原则")).toBeInTheDocument();
      expect(screen.getByText("合理性原则")).toBeInTheDocument();
      expect(screen.getByText("程序正当原则")).toBeInTheDocument();
    });

    it("should show card type badge as 选择题", () => {
      render(
        <Flashcard
          card={choiceCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("选择题")).toBeInTheDocument();
    });

    it("should render choice letters A, B, C, D", () => {
      render(
        <Flashcard
          card={choiceCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("A.")).toBeInTheDocument();
      expect(screen.getByText("B.")).toBeInTheDocument();
      expect(screen.getByText("C.")).toBeInTheDocument();
      expect(screen.getByText("D.")).toBeInTheDocument();
    });

    it("should not show '点击或按空格' hint for choice cards", () => {
      render(
        <Flashcard
          card={choiceCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.queryByText("点击或按空格显示答案")).not.toBeInTheDocument();
    });
  });

  describe("Meta info display", () => {
    it("should show meta_info knowledge when answer is revealed", () => {
      render(
        <Flashcard
          card={metaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText("拓展知识")).toBeInTheDocument();
      expect(screen.getByText(/人民当家作主/)).toBeInTheDocument();
    });

    it("should show exam focus badges", () => {
      render(
        <Flashcard
          card={metaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
        />
      );
      // xingce/shenlun badges were removed, only difficulty and frequency remain
      expect(screen.getByText(/简单/)).toBeInTheDocument();
      expect(screen.getByText(/高频/)).toBeInTheDocument();
    });

    it("should show memory tips", () => {
      render(
        <Flashcard
          card={metaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
        />
      );
      expect(screen.getByText(/根本=人大/)).toBeInTheDocument();
    });
  });

  describe("Keyboard shortcuts", () => {
    it("should toggle answer on space key", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      fireEvent.keyDown(window, { key: " " });
      expect(mockToggle).toHaveBeenCalled();
    });

    it("should toggle answer on Enter key", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
        />
      );
      fireEvent.keyDown(window, { key: "Enter" });
      expect(mockToggle).toHaveBeenCalled();
    });

    it("should rate on number keys when answer is shown", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      fireEvent.keyDown(window, { key: "3" });
      expect(mockRate).toHaveBeenCalledWith(3);
    });

    it("should not rate on number keys when answer is hidden", () => {
      render(
        <Flashcard
          card={qaCard}
          showAnswer={false}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
        />
      );
      fireEvent.keyDown(window, { key: "3" });
      expect(mockRate).not.toHaveBeenCalled();
    });
  });

  describe("Preview intervals", () => {
    it("should show preview intervals on rating buttons", () => {
      const preview = { "1": "1分钟", "2": "10分钟", "3": "1天", "4": "4天" };
      render(
        <Flashcard
          card={qaCard}
          showAnswer={true}
          onToggleAnswer={mockToggle}
          onRate={mockRate}
          preview={preview}
        />
      );
      expect(screen.getByText("1分钟")).toBeInTheDocument();
      expect(screen.getByText("10分钟")).toBeInTheDocument();
      expect(screen.getByText("1天")).toBeInTheDocument();
      expect(screen.getByText("4天")).toBeInTheDocument();
    });
  });
});
