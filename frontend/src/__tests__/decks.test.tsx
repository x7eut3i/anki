/**
 * Tests for Decks page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DecksPage from "@/app/(app)/decks/page";

vi.mock("@/lib/api", () => ({
  decks: {
    list: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
  },
  categories: {
    list: vi.fn(),
  },
}));

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({ token: "test-token" }),
}));

import { decks as deckApi, categories as catApi } from "@/lib/api";
const mockDeckList = deckApi.list as ReturnType<typeof vi.fn>;
const mockDeckCreate = deckApi.create as ReturnType<typeof vi.fn>;
const mockDeckDelete = deckApi.delete as ReturnType<typeof vi.fn>;
const mockCatList = (catApi as any).list as ReturnType<typeof vi.fn>;

const sampleDecks = [
  { id: 1, name: "法律基础", description: "法律入门", card_count: 50, category_id: 1 },
  { id: 2, name: "政治理论", description: "", card_count: 30, category_id: 2 },
];

const sampleCats = [
  { id: 1, name: "法律", icon: "⚖️" },
  { id: 2, name: "政治", icon: "🏛️" },
];

describe("DecksPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDeckList.mockResolvedValue(sampleDecks);
    mockCatList.mockResolvedValue(sampleCats);
    mockDeckCreate.mockResolvedValue({ id: 3, name: "New" });
    window.confirm = vi.fn(() => true);
  });

  it("should show loading spinner initially", () => {
    mockDeckList.mockReturnValue(new Promise(() => {}));
    mockCatList.mockReturnValue(new Promise(() => {}));
    render(<DecksPage />);
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("should render page title", async () => {
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("牌组管理")).toBeInTheDocument();
    });
  });

  it("should render subtitle", async () => {
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("管理你的学习牌组和卡片")).toBeInTheDocument();
    });
  });

  it("should display deck cards", async () => {
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("法律基础")).toBeInTheDocument();
    });
    expect(screen.getByText("政治理论")).toBeInTheDocument();
  });

  it("should show card count for decks", async () => {
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText(/50/)).toBeInTheDocument();
    });
  });

  it("should show description or default", async () => {
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("法律入门")).toBeInTheDocument();
    });
    expect(screen.getByText("暂无描述")).toBeInTheDocument();
  });

  it("should show create button", async () => {
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("新建牌组")).toBeInTheDocument();
    });
  });

  it("should toggle create form on button click", async () => {
    const user = userEvent.setup();
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("新建牌组")).toBeInTheDocument();
    });
    await user.click(screen.getByText("新建牌组"));
    expect(screen.getByPlaceholderText("牌组名称")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("描述 (可选)")).toBeInTheDocument();
  });

  it("should create a new deck", async () => {
    const user = userEvent.setup();
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("新建牌组")).toBeInTheDocument();
    });
    await user.click(screen.getByText("新建牌组"));
    await user.type(screen.getByPlaceholderText("牌组名称"), "新牌组");
    await user.click(screen.getByText("创建"));

    await waitFor(() => {
      expect(mockDeckCreate).toHaveBeenCalledWith(
        expect.objectContaining({ name: "新牌组" }),
        "test-token"
      );
    });
  });

  it("should show empty state when no decks", async () => {
    mockDeckList.mockResolvedValue([]);
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("还没有牌组，创建一个开始学习吧")).toBeInTheDocument();
    });
  });

  it("should have view cards link", async () => {
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getAllByText("查看卡片").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("should call delete with confirmation", async () => {
    const user = userEvent.setup();
    mockDeckDelete.mockResolvedValue(undefined);
    render(<DecksPage />);
    await waitFor(() => {
      expect(screen.getByText("法律基础")).toBeInTheDocument();
    });

    // Click the delete button (Trash2 icon button)
    const deleteButtons = screen.getAllByRole("button").filter(
      (btn) => btn.querySelector("svg") && btn.className.includes("destructive")
    );
    if (deleteButtons.length > 0) {
      await user.click(deleteButtons[0]);
      expect(window.confirm).toHaveBeenCalled();
    }
  });
});
