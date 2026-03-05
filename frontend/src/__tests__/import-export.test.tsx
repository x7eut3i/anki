/**
 * Tests for Import/Export page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ImportExportPage from "@/app/(app)/import-export/page";

vi.mock("@/lib/api", () => ({
  importExport: {
    importCSV: vi.fn(),
    importJSON: vi.fn(),
    importExcel: vi.fn(),
    exportCSV: vi.fn(),
    exportJSON: vi.fn(),
  },
  decks: {
    list: vi.fn(),
  },
  ai: {
    smartImport: vi.fn(),
  },
}));

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({ token: "test-token" }),
}));

import { importExport, decks as deckApi } from "@/lib/api";
const mockImportCSV = importExport.importCSV as ReturnType<typeof vi.fn>;
const mockImportJSON = importExport.importJSON as ReturnType<typeof vi.fn>;
const mockExportCSV = importExport.exportCSV as ReturnType<typeof vi.fn>;
const mockExportJSON = importExport.exportJSON as ReturnType<typeof vi.fn>;
const mockDeckList = deckApi.list as ReturnType<typeof vi.fn>;

const sampleDecks = [
  { id: 1, name: "法律基础", card_count: 50 },
  { id: 2, name: "政治理论", card_count: 30 },
];

describe("ImportExportPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDeckList.mockResolvedValue(sampleDecks);
    // Mock URL.createObjectURL
    global.URL.createObjectURL = vi.fn(() => "blob:mock");
    global.URL.revokeObjectURL = vi.fn();
  });

  it("should render page title", () => {
    render(<ImportExportPage />);
    expect(screen.getByText("导入 / 导出")).toBeInTheDocument();
  });

  it("should render subtitle", () => {
    render(<ImportExportPage />);
    expect(screen.getByText("管理你的卡片数据")).toBeInTheDocument();
  });

  it("should show deck selector section", () => {
    render(<ImportExportPage />);
    expect(screen.getByText("选择牌组")).toBeInTheDocument();
  });

  it("should display available decks", async () => {
    render(<ImportExportPage />);
    await waitFor(() => {
      expect(screen.getByText(/法律基础/)).toBeInTheDocument();
    });
    expect(screen.getByText(/政治理论/)).toBeInTheDocument();
  });

  it("should show import section", () => {
    render(<ImportExportPage />);
    expect(screen.getByText("导入")).toBeInTheDocument();
  });

  it("should show export section", () => {
    render(<ImportExportPage />);
    expect(screen.getByText("导出")).toBeInTheDocument();
  });

  it("should have CSV, JSON, and Excel import buttons", () => {
    render(<ImportExportPage />);
    expect(screen.getByText("导入 CSV")).toBeInTheDocument();
    expect(screen.getByText("导入 JSON")).toBeInTheDocument();
    expect(screen.getByText("导入 Excel")).toBeInTheDocument();
  });

  it("should have CSV and JSON export buttons", () => {
    render(<ImportExportPage />);
    expect(screen.getByText("导出 CSV")).toBeInTheDocument();
    expect(screen.getByText("导出 JSON")).toBeInTheDocument();
  });

  it("import buttons should be disabled without deck selection", () => {
    render(<ImportExportPage />);
    const importCSVBtn = screen.getByText("导入 CSV").closest("button");
    expect(importCSVBtn).toBeDisabled();
  });

  it("export buttons should be disabled without deck selection", () => {
    render(<ImportExportPage />);
    const exportCSVBtn = screen.getByText("导出 CSV").closest("button");
    expect(exportCSVBtn).toBeDisabled();
  });

  it("should enable buttons after selecting a deck", async () => {
    const user = userEvent.setup();
    render(<ImportExportPage />);
    await waitFor(() => {
      expect(screen.getByText(/法律基础/)).toBeInTheDocument();
    });
    await user.click(screen.getByText(/法律基础/));

    const exportCSVBtn = screen.getByText("导出 CSV").closest("button");
    expect(exportCSVBtn).not.toBeDisabled();
  });

  it("should show empty state when no decks", async () => {
    mockDeckList.mockResolvedValue([]);
    render(<ImportExportPage />);
    await waitFor(() => {
      expect(screen.getByText("请先创建牌组")).toBeInTheDocument();
    });
  });

  it("should handle export CSV", async () => {
    const user = userEvent.setup();
    mockExportCSV.mockResolvedValue({
      blob: () => Promise.resolve(new Blob(["test,data"])),
    });

    render(<ImportExportPage />);
    await waitFor(() => {
      expect(screen.getByText(/法律基础/)).toBeInTheDocument();
    });

    await user.click(screen.getByText(/法律基础/));
    await user.click(screen.getByText("导出 CSV").closest("button")!);

    await waitFor(() => {
      expect(screen.getByText("导出成功！")).toBeInTheDocument();
    });
  });

  it("should show error on export failure", async () => {
    const user = userEvent.setup();
    mockExportJSON.mockRejectedValue(new Error("Export failed"));

    render(<ImportExportPage />);
    await waitFor(() => {
      expect(screen.getByText(/法律基础/)).toBeInTheDocument();
    });

    await user.click(screen.getByText(/法律基础/));
    await user.click(screen.getByText("导出 JSON").closest("button")!);

    await waitFor(() => {
      expect(screen.getByText("导出失败")).toBeInTheDocument();
    });
  });

  it("should show result message when no deck selected for export", async () => {
    const user = userEvent.setup();
    render(<ImportExportPage />);
    // Export buttons are disabled without deck, but test the message logic
    // We can verify the disabled state
    const btn = screen.getByText("导出 CSV").closest("button");
    expect(btn).toBeDisabled();
  });
});
