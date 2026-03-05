/**
 * Tests for Zustand stores: useAuthStore and useStudyStore
 */
import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore, useStudyStore } from "@/lib/store";
import { act } from "@testing-library/react";

describe("useAuthStore", () => {
  beforeEach(() => {
    // Reset store to initial state
    act(() => {
      useAuthStore.setState({ token: null, user: null });
    });
  });

  it("should have null initial state", () => {
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it("setAuth should set token and user", () => {
    act(() => {
      useAuthStore.getState().setAuth("test-token-123", { username: "admin", email: "a@b.com" });
    });
    const state = useAuthStore.getState();
    expect(state.token).toBe("test-token-123");
    expect(state.user).toEqual({ username: "admin", email: "a@b.com" });
  });

  it("logout should clear token and user", () => {
    act(() => {
      useAuthStore.getState().setAuth("token", { username: "u" });
    });
    expect(useAuthStore.getState().token).toBe("token");

    act(() => {
      useAuthStore.getState().logout();
    });
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
  });

  it("setAuth can be called multiple times", () => {
    act(() => {
      useAuthStore.getState().setAuth("token1", { username: "user1" });
    });
    expect(useAuthStore.getState().user.username).toBe("user1");

    act(() => {
      useAuthStore.getState().setAuth("token2", { username: "user2" });
    });
    expect(useAuthStore.getState().token).toBe("token2");
    expect(useAuthStore.getState().user.username).toBe("user2");
  });
});

describe("useStudyStore", () => {
  beforeEach(() => {
    act(() => {
      useStudyStore.getState().reset();
    });
  });

  it("should have correct initial state", () => {
    const state = useStudyStore.getState();
    expect(state.currentCards).toEqual([]);
    expect(state.currentIndex).toBe(0);
    expect(state.showAnswer).toBe(false);
    expect(state.sessionId).toBeNull();
    expect(state.mode).toBe("review");
  });

  it("setCards should populate cards and reset index", () => {
    const cards = [
      { id: 1, front: "Q1", back: "A1" },
      { id: 2, front: "Q2", back: "A2" },
    ];
    act(() => {
      useStudyStore.getState().setCards(cards);
    });
    const state = useStudyStore.getState();
    expect(state.currentCards).toHaveLength(2);
    expect(state.currentIndex).toBe(0);
    expect(state.showAnswer).toBe(false);
  });

  it("nextCard should advance index", () => {
    const cards = [
      { id: 1, front: "Q1", back: "A1" },
      { id: 2, front: "Q2", back: "A2" },
      { id: 3, front: "Q3", back: "A3" },
    ];
    act(() => {
      useStudyStore.getState().setCards(cards);
    });
    act(() => {
      useStudyStore.getState().nextCard();
    });
    expect(useStudyStore.getState().currentIndex).toBe(1);
    expect(useStudyStore.getState().showAnswer).toBe(false);
  });

  it("nextCard should not exceed card count", () => {
    const cards = [{ id: 1, front: "Q1", back: "A1" }];
    act(() => {
      useStudyStore.getState().setCards(cards);
    });
    act(() => {
      useStudyStore.getState().nextCard();
    });
    act(() => {
      useStudyStore.getState().nextCard();
    });
    expect(useStudyStore.getState().currentIndex).toBe(0);
  });

  it("toggleAnswer should flip showAnswer", () => {
    expect(useStudyStore.getState().showAnswer).toBe(false);
    act(() => {
      useStudyStore.getState().toggleAnswer();
    });
    expect(useStudyStore.getState().showAnswer).toBe(true);
    act(() => {
      useStudyStore.getState().toggleAnswer();
    });
    expect(useStudyStore.getState().showAnswer).toBe(false);
  });

  it("setSession should set sessionId and mode", () => {
    act(() => {
      useStudyStore.getState().setSession(42, "quiz");
    });
    const state = useStudyStore.getState();
    expect(state.sessionId).toBe(42);
    expect(state.mode).toBe("quiz");
  });

  it("reset should clear all state", () => {
    act(() => {
      useStudyStore.getState().setCards([{ id: 1 }]);
      useStudyStore.getState().nextCard();
      useStudyStore.getState().toggleAnswer();
      useStudyStore.getState().setSession(5, "mix");
    });
    act(() => {
      useStudyStore.getState().reset();
    });
    const state = useStudyStore.getState();
    expect(state.currentCards).toEqual([]);
    expect(state.currentIndex).toBe(0);
    expect(state.showAnswer).toBe(false);
    expect(state.sessionId).toBeNull();
    expect(state.mode).toBe("review");
  });

  it("nextCard should reset showAnswer to false", () => {
    act(() => {
      useStudyStore.getState().setCards([{ id: 1 }, { id: 2 }]);
      useStudyStore.getState().toggleAnswer();
    });
    expect(useStudyStore.getState().showAnswer).toBe(true);
    act(() => {
      useStudyStore.getState().nextCard();
    });
    expect(useStudyStore.getState().showAnswer).toBe(false);
  });
});
