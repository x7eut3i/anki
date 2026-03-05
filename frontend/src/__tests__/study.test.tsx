/**
 * Tests for Study page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StudyPage from "@/app/(app)/study/page";

vi.mock("@/lib/api", () => ({
  review: {
    getDue: vi.fn(),
    answer: vi.fn(),
    preview: vi.fn(),
    createSession: vi.fn(),
    getActiveSession: vi.fn(),
    updateProgress: vi.fn(),
  },
}));

const mockSetCards = vi.fn();
const mockNextCard = vi.fn();
const mockToggleAnswer = vi.fn();
const mockReset = vi.fn();

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({ token: "test-token" }),
  useStudyStore: () => ({
    currentCards: [],
    currentIndex: 0,
    showAnswer: false,
    setCards: mockSetCards,
    nextCard: mockNextCard,
    toggleAnswer: mockToggleAnswer,
    reset: mockReset,
  }),
}));

import { review } from "@/lib/api";
const mockGetDue = review.getDue as ReturnType<typeof vi.fn>;
const mockAnswer = review.answer as ReturnType<typeof vi.fn>;
const mockPreview = review.preview as ReturnType<typeof vi.fn>;
const mockCreateSession = review.createSession as ReturnType<typeof vi.fn>;
const mockGetActiveSession = review.getActiveSession as ReturnType<typeof vi.fn>;
const mockUpdateProgress = review.updateProgress as ReturnType<typeof vi.fn>;

describe("StudyPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPreview.mockResolvedValue({
      "1": "1分", "2": "10分", "3": "1天", "4": "4天",
    });
    mockGetActiveSession.mockResolvedValue(null);
    mockCreateSession.mockResolvedValue({ id: 1, total_cards: 5 });
    mockUpdateProgress.mockResolvedValue({ cards_reviewed: 1, cards_correct: 1 });
  });

  it("should show loading spinner initially", () => {
    mockGetActiveSession.mockReturnValue(new Promise(() => {}));
    render(<StudyPage />);
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("should show completion when no cards due", async () => {
    mockCreateSession.mockResolvedValue({ id: 1, total_cards: 0 });
    mockGetDue.mockResolvedValue({ cards: [] });
    render(<StudyPage />);
    await waitFor(() => {
      expect(screen.getByText("太棒了！")).toBeInTheDocument();
    });
    expect(screen.getByText("今天没有待复习的卡片了")).toBeInTheDocument();
  });

  it("should show completion screen elements", async () => {
    mockCreateSession.mockResolvedValue({ id: 1, total_cards: 0 });
    mockGetDue.mockResolvedValue({ cards: [] });
    render(<StudyPage />);
    await waitFor(() => {
      expect(screen.getByText("返回仪表盘")).toBeInTheDocument();
    });
    expect(screen.getByText("再来一轮")).toBeInTheDocument();
  });

  it("should call createSession and getDue on mount", async () => {
    mockGetDue.mockResolvedValue({ cards: [] });
    render(<StudyPage />);
    await waitFor(() => {
      expect(mockCreateSession).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(mockGetDue).toHaveBeenCalledWith(
        expect.objectContaining({ limit: 50 }),
        "test-token"
      );
    });
  });

  it("should set cards when due cards exist", async () => {
    const cards = [
      { id: 1, front: "Q1", back: "A1", distractors: "" },
    ];
    mockCreateSession.mockResolvedValue({ id: 1, total_cards: 1 });
    mockGetDue.mockResolvedValue({ cards });
    render(<StudyPage />);
    await waitFor(() => {
      expect(mockSetCards).toHaveBeenCalledWith(cards);
    });
  });

  it("should call reset on unmount", () => {
    mockCreateSession.mockResolvedValue({ id: 1, total_cards: 0 });
    mockGetDue.mockResolvedValue({ cards: [] });
    const { unmount } = render(<StudyPage />);
    unmount();
    expect(mockReset).toHaveBeenCalled();
  });
});
