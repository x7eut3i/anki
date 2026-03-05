/**
 * Tests for Login page
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/app/login/page";

// Mock API
vi.mock("@/lib/api", () => ({
  auth: {
    login: vi.fn(),
    register: vi.fn(),
    me: vi.fn(),
  },
}));

// Mock store
const mockSetAuth = vi.fn();
vi.mock("@/lib/store", () => ({
  useAuthStore: () => ({
    setAuth: mockSetAuth,
  }),
}));

// Get mocked API
import { auth } from "@/lib/api";
const mockLogin = auth.login as ReturnType<typeof vi.fn>;
const mockRegister = auth.register as ReturnType<typeof vi.fn>;
const mockMe = auth.me as ReturnType<typeof vi.fn>;

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render login form by default", () => {
    render(<LoginPage />);
    expect(screen.getByText("Anki Cards")).toBeInTheDocument();
    expect(screen.getByText("登录你的账号")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("请输入用户名")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("请输入密码")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
  });

  it("should not show email field in login mode", () => {
    render(<LoginPage />);
    expect(screen.queryByPlaceholderText("请输入邮箱")).not.toBeInTheDocument();
  });

  it("should toggle to register mode", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await user.click(screen.getByText("注册"));
    expect(screen.getByText("创建新账号")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("请输入邮箱")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "注册" })).toBeInTheDocument();
  });

  it("should toggle back to login mode", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await user.click(screen.getByText("注册"));
    expect(screen.getByText("创建新账号")).toBeInTheDocument();
    await user.click(screen.getByText("登录"));
    expect(screen.getByText("登录你的账号")).toBeInTheDocument();
  });

  it("should call login API on submit", async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValue({ access_token: "tok", token_type: "bearer" });
    mockMe.mockResolvedValue({ id: 1, username: "admin" });

    render(<LoginPage />);
    await user.type(screen.getByPlaceholderText("请输入用户名"), "admin");
    await user.type(screen.getByPlaceholderText("请输入密码"), "password123");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith("admin", "password123");
      expect(mockMe).toHaveBeenCalledWith("tok");
      expect(mockSetAuth).toHaveBeenCalledWith("tok", { id: 1, username: "admin" });
    });
  });

  it("should call register API when in register mode", async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValue({ access_token: "new-tok", token_type: "bearer" });
    mockMe.mockResolvedValue({ id: 2, username: "newuser" });

    render(<LoginPage />);
    await user.click(screen.getByText("注册"));
    await user.type(screen.getByPlaceholderText("请输入用户名"), "newuser");
    await user.type(screen.getByPlaceholderText("请输入邮箱"), "new@test.com");
    await user.type(screen.getByPlaceholderText("请输入密码"), "pass123456");
    await user.click(screen.getByRole("button", { name: "注册" }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        username: "newuser",
        email: "new@test.com",
        password: "pass123456",
      });
    });
  });

  it("should display error on login failure", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValue(new Error("用户名或密码错误"));

    render(<LoginPage />);
    await user.type(screen.getByPlaceholderText("请输入用户名"), "wrong");
    await user.type(screen.getByPlaceholderText("请输入密码"), "wrong123");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("用户名或密码错误")).toBeInTheDocument();
    });
  });

  it("should clear error when switching modes", async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValue(new Error("错误"));

    render(<LoginPage />);
    await user.type(screen.getByPlaceholderText("请输入用户名"), "bad");
    await user.type(screen.getByPlaceholderText("请输入密码"), "bad123");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(screen.getByText("错误")).toBeInTheDocument();
    });

    await user.click(screen.getByText("注册"));
    expect(screen.queryByText("错误")).not.toBeInTheDocument();
  });

  it("should have Brain icon", () => {
    render(<LoginPage />);
    // The Brain icon is rendered inside a div
    const iconContainer = screen.getByText("Anki Cards").closest("div");
    expect(iconContainer).toBeInTheDocument();
  });
});
