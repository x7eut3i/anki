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
  reviewedIndices: Set<number>;  // tracks which card indices have been rated
  setCards: (cards: any[]) => void;
  initSession: (cards: any[], startIndex: number, reviewed: Set<number>) => void;
  nextCard: () => void;
  prevCard: () => void;
  goToCard: (index: number) => void;
  markReviewed: (index: number) => void;
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
  reviewedIndices: new Set(),
  setCards: (cards) => set({ currentCards: cards, currentIndex: 0, showAnswer: false, reviewedIndices: new Set() }),
  initSession: (cards, startIndex, reviewed) => set({
    currentCards: cards,
    currentIndex: startIndex,
    showAnswer: false,
    reviewedIndices: reviewed,
  }),
  nextCard: () =>
    set((s) => ({
      currentIndex: Math.min(s.currentIndex + 1, s.currentCards.length - 1),
      showAnswer: false,
    })),
  prevCard: () =>
    set((s) => ({
      currentIndex: Math.max(s.currentIndex - 1, 0),
      showAnswer: false,
    })),
  goToCard: (index) =>
    set((s) => ({
      currentIndex: Math.max(0, Math.min(index, s.currentCards.length - 1)),
      showAnswer: false,
    })),
  markReviewed: (index) =>
    set((s) => {
      const newSet = new Set(s.reviewedIndices);
      newSet.add(index);
      return { reviewedIndices: newSet };
    }),
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
      reviewedIndices: new Set(),
    }),
}));
