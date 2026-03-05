/**
 * Tests for Settings page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsPage from "@/app/(app)/settings/page";

const mockLogout = vi.fn();

vi.mock("@/lib/api", () => ({
  auth: {
    me: vi.fn(),
  },
}));

vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({
    token: "test-token",
    user: { username: "admin", email: "admin@test.com" },
    setAuth: vi.fn(),
    logout: mockLogout,
  }),
}));

import { auth } from "@/lib/api";
const mockMe = auth.me as ReturnType<typeof vi.fn>;

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMe.mockResolvedValue({
      username: "admin",
      email: "admin@test.com",
      daily_new_limit: 30,
      desired_retention: 0.85,
    });
    // Mock window.location.href for logout
    Object.defineProperty(window, "location", {
      writable: true,
      value: { href: "" },
    });
  });

  it("should render page title", () => {
    render(<SettingsPage />);
    expect(screen.getByText("设置")).toBeInTheDocument();
  });

  it("should render subtitle", () => {
    render(<SettingsPage />);
    expect(screen.getByText("个人偏好和学习设置")).toBeInTheDocument();
  });

  it("should show profile section", () => {
    render(<SettingsPage />);
    expect(screen.getByText("个人信息")).toBeInTheDocument();
  });

  it("should show study settings section", () => {
    render(<SettingsPage />);
    expect(screen.getByText("学习设置")).toBeInTheDocument();
  });

  it("should load user profile", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(mockMe).toHaveBeenCalledWith("test-token");
    });
  });

  it("should display username (disabled)", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      const usernameInput = screen.getByDisplayValue("admin");
      expect(usernameInput).toBeInTheDocument();
      expect(usernameInput).toBeDisabled();
    });
  });

  it("should have daily new cards input", () => {
    render(<SettingsPage />);
    expect(screen.getByText("每日新卡数量")).toBeInTheDocument();
  });

  it("should have desired retention input", () => {
    render(<SettingsPage />);
    expect(screen.getByText("期望记忆保持率")).toBeInTheDocument();
  });

  it("should show FSRS explanation", () => {
    render(<SettingsPage />);
    expect(screen.getByText(/FSRS 目标保持率/)).toBeInTheDocument();
  });

  it("should have save settings button", () => {
    render(<SettingsPage />);
    expect(screen.getByText("保存设置")).toBeInTheDocument();
  });

  it("should have logout button", () => {
    render(<SettingsPage />);
    expect(screen.getByText("退出登录")).toBeInTheDocument();
  });

  it("should call logout and redirect on logout click", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);
    await user.click(screen.getByText("退出登录"));
    expect(mockLogout).toHaveBeenCalled();
    expect(window.location.href).toBe("/login");
  });
});
