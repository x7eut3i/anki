/**
 * Tests for Sidebar component
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// We need to re-mock next/navigation for Sidebar's usePathname usage
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({
    user: { username: "TestUser", email: "test@example.com" },
    logout: vi.fn(),
  }),
}));

import Sidebar from "@/components/sidebar";

describe("Sidebar", () => {
  it("should render app title", () => {
    render(<Sidebar />);
    expect(screen.getByText("Anki Cards")).toBeInTheDocument();
  });

  it("should render FSRS subtitle", () => {
    render(<Sidebar />);
    expect(screen.getByText("FSRS智能复习")).toBeInTheDocument();
  });

  it("should render all navigation items", () => {
    render(<Sidebar />);
    expect(screen.getAllByText("仪表盘").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("学习").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("模拟测试").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("牌组管理").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("导入导出").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("AI助手").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("文章精读").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("设置").length).toBeGreaterThanOrEqual(1);
  });

  it("should display user initial", () => {
    render(<Sidebar />);
    expect(screen.getByText("T")).toBeInTheDocument(); // "TestUser"[0].toUpperCase()
  });

  it("should display username", () => {
    render(<Sidebar />);
    expect(screen.getByText("TestUser")).toBeInTheDocument();
  });

  it("should display user email", () => {
    render(<Sidebar />);
    expect(screen.getByText("test@example.com")).toBeInTheDocument();
  });

  it("should have correct navigation links", () => {
    render(<Sidebar />);
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/dashboard");
    expect(hrefs).toContain("/study");
    expect(hrefs).toContain("/quiz");
    expect(hrefs).toContain("/decks");
    expect(hrefs).toContain("/import-export");
    expect(hrefs).toContain("/ai");
    expect(hrefs).toContain("/reading");
    expect(hrefs).toContain("/settings");
  });

  it("should render logout button", () => {
    render(<Sidebar />);
    // LogOut icon is in a button
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });
});
