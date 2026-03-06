/**
 * Global auth & app state using Zustand.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { initTimezone } from "./timezone";

// ---------------------------------------------------------------------------
// Auth store
// ---------------------------------------------------------------------------

interface AuthState {
  token: string | null;
  user: any | null;
  setAuth: (token: string, user: any) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => {
        if (user?.timezone) initTimezone(user.timezone);
        set({ token, user });
      },
      logout: () => set({ token: null, user: null }),
    }),
    { name: "anki-auth" }
  )
);

// ---------------------------------------------------------------------------
// Study session store
// ---------------------------------------------------------------------------

interface StudyState {
  currentCards: any[];
  currentIndex: number;
  showAnswer: boolean;
  sessionId: number | null;
  mode: "review" | "mix" | "quiz";
  setCards: (cards: any[]) => void;
  nextCard: () => void;
  toggleAnswer: () => void;
  setSession: (id: number, mode: "review" | "mix" | "quiz") => void;
  updateCurrentCard: (patch: Partial<any>) => void;
  reset: () => void;
}

export const useStudyStore = create<StudyState>((set) => ({
  currentCards: [],
  currentIndex: 0,
  showAnswer: false,
  sessionId: null,
  mode: "review",
  setCards: (cards) => set({ currentCards: cards, currentIndex: 0, showAnswer: false }),
  nextCard: () =>
    set((s) => ({
      currentIndex: Math.min(s.currentIndex + 1, s.currentCards.length - 1),
      showAnswer: false,
    })),
  toggleAnswer: () => set((s) => ({ showAnswer: !s.showAnswer })),
  setSession: (id, mode) => set({ sessionId: id, mode }),
  updateCurrentCard: (patch) =>
    set((s) => {
      const cards = [...s.currentCards];
      if (cards[s.currentIndex]) {
        cards[s.currentIndex] = { ...cards[s.currentIndex], ...patch };
      }
      return { currentCards: cards };
    }),
  reset: () =>
    set({
      currentCards: [],
      currentIndex: 0,
      showAnswer: false,
      sessionId: null,
      mode: "review",
    }),
}));
