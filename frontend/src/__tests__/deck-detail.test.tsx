/**
 * Tests for Deck Detail page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DeckDetailPage from "@/app/(app)/deck-detail/page";

// Override useSearchParams for this test
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => "/deck-detail",
  useSearchParams: () => {
    const params = new URLSearchParams("id=5");
    return params;
  },
}));

vi.mock("@/lib/api", () => ({
  decks: {
    get: vi.fn(),
  },
  cards: {
    list: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({ token: "test-token" }),
}));

import { decks as deckApi, cards as cardApi } from "@/lib/api";
const mockDeckGet = deckApi.get as ReturnType<typeof vi.fn>;
const mockCardList = cardApi.list as ReturnType<typeof vi.fn>;
const mockCardDelete = cardApi.delete as ReturnType<typeof vi.fn>;

const sampleDeck = { id: 5, name: "法律牌组", description: "法律相关卡片" };
const sampleCards = [
  {
    id: 101,
    front: "什么是宪法？",
    back: "宪法是根本大法",
    distractors: "",
    state: 0,
    reps: 0,
    lapses: 0,
    due: new Date().toISOString(),
  },
  {
    id: 102,
    front: "什么是行政法？",
    back: "行政法是管理国家行政的法律",
    distractors: '["民法", "刑法", "商法"]',
    state: 2,
    reps: 5,
    lapses: 1,
    due: new Date(Date.now() + 86400000).toISOString(),
    is_suspended: false,
  },
];

describe("DeckDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDeckGet.mockResolvedValue(sampleDeck);
    mockCardList.mockResolvedValue({ cards: sampleCards });
    window.confirm = vi.fn(() => true);
  });

  it("should render deck name", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("法律牌组")).toBeInTheDocument();
    });
  });

  it("should render deck description", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("法律相关卡片")).toBeInTheDocument();
    });
  });

  it("should render card list", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("什么是宪法？")).toBeInTheDocument();
    });
    expect(screen.getByText("什么是行政法？")).toBeInTheDocument();
  });

  it("should show stats cards", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("总卡片数")).toBeInTheDocument();
    });
    expect(screen.getByText("新卡片")).toBeInTheDocument();
    expect(screen.getByText("待复习")).toBeInTheDocument();
  });

  it("should display card count", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      // Total = 2 cards
      const totalCards = screen.getByText("2");
      expect(totalCards).toBeInTheDocument();
    });
  });

  it("should show card type badges", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("问答题")).toBeInTheDocument();
      expect(screen.getByText("选择题")).toBeInTheDocument();
    });
  });

  it("should show card state badges", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      // State badges are visible on the collapsed card headers
      expect(screen.getByText("新")).toBeInTheDocument(); // card with state=0
      expect(screen.getByText("复习")).toBeInTheDocument(); // card with state=2
    });
  });

  it("should have start study button", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("开始学习")).toBeInTheDocument();
    });
  });

  it("should have back to decks link", async () => {
    render(<DeckDetailPage />);
    await waitFor(() => {
      const backLink = screen.getAllByRole("link").find(
        (el) => el.getAttribute("href") === "/decks"
      );
      expect(backLink).toBeDefined();
    });
  });

  it("should show 暂无描述 when no description", async () => {
    mockDeckGet.mockResolvedValue({ id: 5, name: "Test", description: "" });
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("暂无描述")).toBeInTheDocument();
    });
  });

  it("should show empty state when no cards", async () => {
    mockCardList.mockResolvedValue({ cards: [] });
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("这个牌组还没有卡片")).toBeInTheDocument();
    });
  });

  it("should handle deck not found", async () => {
    mockDeckGet.mockResolvedValue(null);
    mockCardList.mockResolvedValue({ cards: [] });
    render(<DeckDetailPage />);
    await waitFor(() => {
      expect(screen.getByText("牌组不存在")).toBeInTheDocument();
    });
  });
});
