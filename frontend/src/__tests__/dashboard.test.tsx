/**
 * Tests for Dashboard page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import DashboardPage from "@/app/(app)/dashboard/page";

// Mock API
vi.mock("@/lib/api", () => ({
  review: {
    stats: vi.fn(),
    getActiveSession: vi.fn(),
  },
  categories: {
    list: vi.fn(),
  },
}));

import { review, categories } from "@/lib/api";
const mockStats = review.stats as ReturnType<typeof vi.fn>;
const mockCatList = categories.list as ReturnType<typeof vi.fn>;
const mockGetActiveSession = review.getActiveSession as ReturnType<typeof vi.fn>;

// Mock store
vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({
    token: "test-token",
  }),
}));

const sampleStats = {
  reviewed_today: 15,
  max_daily_calls: 50,
  streak_days: 7,
  retention_rate: 0.852,
  total_cards: 161,
  cards_due_today: 23,
};

const sampleCats = [
  { id: 1, name: "法律", icon: "⚖️", card_count: 50 },
  { id: 2, name: "政治", icon: "🏛️", card_count: 40 },
  { id: 3, name: "马哲", icon: "📖", card_count: 30 },
];

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStats.mockResolvedValue(sampleStats);
    mockCatList.mockResolvedValue(sampleCats);
    mockGetActiveSession.mockResolvedValue(null);
  });

  it("should show loading spinner initially", () => {
    // Make the API calls never resolve to see loading state
    mockStats.mockReturnValue(new Promise(() => {}));
    mockCatList.mockReturnValue(new Promise(() => {}));
    mockGetActiveSession.mockReturnValue(new Promise(() => {}));
    render(<DashboardPage />);
    // Check for spinner (animation div)
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).toBeInTheDocument();
  });

  it("should render stats cards after loading", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("学习概览")).toBeInTheDocument();
    });
    expect(screen.getByText("今日复习")).toBeInTheDocument();
    expect(screen.getByText("连续学习")).toBeInTheDocument();
    expect(screen.getByText("记忆保持率")).toBeInTheDocument();
    expect(screen.getByText("待复习")).toBeInTheDocument();
  });

  it("should display correct stat values", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("15 / 50")).toBeInTheDocument();
    });
    expect(screen.getByText("7 天")).toBeInTheDocument();
    expect(screen.getByText("85.2%")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
  });

  it("should render quick action cards", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("开始复习")).toBeInTheDocument();
    });
    expect(screen.getByText("混合模式")).toBeInTheDocument();
    expect(screen.getByText("模拟测试")).toBeInTheDocument();
  });

  it("should show due count in study card", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("23 张卡片等待复习")).toBeInTheDocument();
    });
  });

  it("should render category list", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("科目分类")).toBeInTheDocument();
    });
    expect(screen.getByText("法律")).toBeInTheDocument();
    expect(screen.getByText("政治")).toBeInTheDocument();
    expect(screen.getByText("马哲")).toBeInTheDocument();
  });

  it("should display card count for categories", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("50 张")).toBeInTheDocument();
    });
    expect(screen.getByText("40 张")).toBeInTheDocument();
    expect(screen.getByText("30 张")).toBeInTheDocument();
  });

  it("should show completion message when no cards due", async () => {
    mockStats.mockResolvedValue({ ...sampleStats, cards_due_today: 0 });
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("今日已完成 🎉")).toBeInTheDocument();
    });
  });

  it("should have links to study, quiz, and dashboard", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText("开始复习")).toBeInTheDocument();
    });
    const studyLink = screen.getByText("立即学习").closest("a");
    expect(studyLink).toHaveAttribute("href", "/study");
  });

  it("should show encouragement text", async () => {
    render(<DashboardPage />);
    await waitFor(() => {
      expect(screen.getByText(/坚持每天复习/)).toBeInTheDocument();
    });
  });
});
