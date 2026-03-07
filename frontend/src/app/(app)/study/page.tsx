"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { useAuthStore, useStudyStore } from "@/lib/store";
import { review } from "@/lib/api";
import Flashcard from "@/components/flashcard";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ArrowLeft, Trophy, RotateCcw, PlayCircle } from "lucide-react";
import Link from "next/link";
import { CardTagManager } from "@/components/card-detail";

export default function StudyPage() {
  const { token } = useAuthStore();
  const params = useSearchParams();
  const mode = (params.get("mode") as "review" | "mix") || "review";
  const categoryParam = params.get("category");
  const categoryIds = categoryParam ? categoryParam.split(",").map(Number).filter(Boolean) : [];
  const deckId = params.get("deck");
  const deckIdsParam = params.get("deck_ids");
  const deckIds = deckIdsParam ? deckIdsParam.split(",").map(Number).filter(Boolean) : [];
  const tagIdsParam = params.get("tag_ids"); // comma-separated tag IDs
  const tagIds = tagIdsParam ? tagIdsParam.split(",").map(Number).filter(Boolean) : [];
  // When studying a specific category from dashboard, exclude AI-deck cards
  const excludeAi = params.get("exclude_ai") === "1";

  const {
    currentCards,
    currentIndex,
    showAnswer,
    setCards,
    nextCard,
    toggleAnswer,
    updateCurrentCard,
    reset,
  } = useStudyStore();

  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<any>(null);
  const [completed, setCompleted] = useState(false);
  const [reviewedCount, setReviewedCount] = useState(0);
  const [pendingSession, setPendingSession] = useState<any>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [cardStartTime, setCardStartTime] = useState<number>(Date.now());

  // 60/40 Q&A/choice ratio: pre-compute for each card
  const [forceTypeMap, setForceTypeMap] = useState<Record<number, "qa" | "choice">>({});

  // Compute 60% Q&A / 40% Choice ratio for review & mix modes
  const computeForceTypes = useCallback((cards: any[]) => {
    const map: Record<number, "qa" | "choice"> = {};
    cards.forEach((c) => {
      // 实词辨析 cards: always choice (selection-based by nature)
      if (c.category_name === "实词辨析") {
        map[c.id] = "choice";
      } else {
        // In review/mix mode, 60% Q&A, 40% choice
        map[c.id] = Math.random() < 0.6 ? "qa" : "choice";
      }
    });
    setForceTypeMap(map);
  }, []);

  // Check for an unfinished session first (exclude quiz sessions)
  const checkActiveSession = useCallback(async () => {
    if (!token) return;
    try {
      const session = await review.getActiveSession(token);
      if (session && !session.is_completed && session.mode !== "quiz") {
        const remaining = JSON.parse(session.remaining_card_ids || "[]");
        if (remaining.length > 0) {
          setPendingSession(session);
          setLoading(false);
          return true;
        }
      }
    } catch {
      // No active session, proceed normally
    }
    return false;
  }, [token]);

  // Load due cards (fresh session)
  const loadCards = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setCompleted(false);
    setPendingSession(null);
    try {
      // Create a study session which fetches and stores due cards
      const cardLimit = parseInt(params.get("limit") || "50") || 50;
      const sessionParams: any = { mode: mode === "mix" ? "mix" : "review", card_limit: cardLimit };
      if (categoryIds.length > 0) sessionParams.category_ids = categoryIds;
      if (deckIds.length > 0) sessionParams.deck_ids = deckIds;
      else if (deckId) sessionParams.deck_id = parseInt(deckId);
      if (tagIds.length > 0) sessionParams.tag_ids = tagIds;
      if (excludeAi) sessionParams.exclude_ai_decks = true;
      const session = await review.createSession(sessionParams, token);
      if (session && session.total_cards > 0) {
        setSessionId(session.id);
        // Now fetch the actual card data
        const dueParams: any = { limit: cardLimit };
        if (categoryIds.length > 0) dueParams.category_ids = categoryIds;
        if (deckIds.length > 0) dueParams.deck_ids = deckIds;
        else if (deckId) dueParams.deck_id = parseInt(deckId);
        if (tagIds.length > 0) dueParams.tag_ids = tagIds;
        if (excludeAi) dueParams.exclude_ai_decks = true;
        const data = await review.getDue(dueParams, token);
        if (data.cards && data.cards.length > 0) {
          setCards(data.cards);
          computeForceTypes(data.cards);
        } else {
          setCompleted(true);
        }
      } else {
        setCompleted(true);
      }
    } catch {
      // Fallback: just fetch due cards without session
      try {
        const fallbackParams: any = { limit: 50 };
        if (categoryIds.length > 0) fallbackParams.category_ids = categoryIds;
        if (deckIds.length > 0) fallbackParams.deck_ids = deckIds;
        else if (deckId) fallbackParams.deck_id = parseInt(deckId);
        if (tagIds.length > 0) fallbackParams.tag_ids = tagIds;
        if (excludeAi) fallbackParams.exclude_ai_decks = true;
        const data = await review.getDue(fallbackParams, token);
        if (data.cards && data.cards.length > 0) {
          setCards(data.cards);
          computeForceTypes(data.cards);
        } else {
          setCompleted(true);
        }
      } catch {
        setCompleted(true);
      }
    } finally {
      setLoading(false);
    }
  }, [token, setCards, categoryIds, deckId, deckIds, mode]);

  // Resume an unfinished session
  const resumeSession = useCallback(async () => {
    if (!token || !pendingSession) return;
    setLoading(true);
    setPendingSession(null);
    try {
      setSessionId(pendingSession.id);
      const remaining = JSON.parse(pendingSession.remaining_card_ids || "[]");
      // Fetch the actual card data for remaining card IDs
      const data = await review.getDue({ limit: 200 }, token);
      const remainingSet = new Set(remaining);
      const resumeCards = (data.cards || []).filter((c: any) => remainingSet.has(c.id));
      if (resumeCards.length > 0) {
        setCards(resumeCards);
        setReviewedCount(pendingSession.cards_reviewed || 0);
      } else {
        // Cards may have been reviewed already, start fresh
        await loadCards();
      }
    } finally {
      setLoading(false);
    }
  }, [token, pendingSession, setCards, loadCards]);

  useEffect(() => {
    const init = async () => {
      const wantsResume = params.get("resume") === "1";
      const hasSpecificTarget = categoryIds.length > 0 || !!deckId || deckIds.length > 0 || mode === "mix";

      if (wantsResume) {
        // Coming from dashboard "继续学习" — auto-resume without showing prompt
        if (!token) return;
        try {
          const session = await review.getActiveSession(token);
          if (session && !session.is_completed && session.mode !== "quiz") {
            const remaining = JSON.parse(session.remaining_card_ids || "[]");
            if (remaining.length > 0) {
              // Auto-resume directly
              setSessionId(session.id);
              const data = await review.getDue({ limit: 200 }, token);
              const remainingSet = new Set(remaining);
              const resumeCards = (data.cards || []).filter((c: any) => remainingSet.has(c.id));
              if (resumeCards.length > 0) {
                setCards(resumeCards);
                setReviewedCount(session.cards_reviewed || 0);
                setLoading(false);
                return;
              }
            }
          }
        } catch {
          // Fall through to loadCards
        }
        await loadCards();
      } else if (!hasSpecificTarget) {
        // No specific target — just start fresh, don't prompt about old sessions
        await loadCards();
      } else {
        // User chose a specific deck/category/mode — start fresh directly
        await loadCards();
      }
    };
    init();
    return () => reset();
  }, []);

  // Load preview for current card & reset timer
  useEffect(() => {
    if (!token || !currentCards[currentIndex]) return;
    setCardStartTime(Date.now());
    review
      .preview(currentCards[currentIndex].id, token)
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [token, currentCards, currentIndex]);

  const handleRate = async (rating: number) => {
    if (!token) return;
    const card = currentCards[currentIndex];
    const durationMs = Math.min(Date.now() - cardStartTime, 600000); // cap at 10 min
    try {
      await review.answer({ card_id: card.id, rating, review_duration_ms: durationMs }, token);
      setReviewedCount((c) => c + 1);

      // Update session progress if we have an active session
      if (sessionId) {
        try {
          await review.updateProgress(sessionId, card.id, rating >= 3, token);
        } catch {
          // Non-critical: session tracking failure shouldn't block study
        }
      }

      if (currentIndex + 1 < currentCards.length) {
        nextCard();
      } else {
        setCompleted(true);
      }
    } catch (err) {
      console.error("Review failed:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  // Prompt to resume an unfinished session
  if (pendingSession) {
    const remaining = JSON.parse(pendingSession.remaining_card_ids || "[]");
    const reviewed = pendingSession.cards_reviewed || 0;
    const total = pendingSession.total_cards || 0;

    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6">
        <div className="rounded-full bg-blue-100 p-6">
          <PlayCircle className="h-16 w-16 text-blue-600" />
        </div>
        <h2 className="text-2xl font-bold">发现未完成的学习</h2>
        <p className="text-muted-foreground text-center">
          上次学习了 {reviewed}/{total} 张卡片，还剩 {remaining.length} 张未完成
        </p>
        <div className="flex gap-3">
          <Button onClick={resumeSession}>
            <PlayCircle className="mr-2 h-4 w-4" />
            继续学习
          </Button>
          <Button variant="outline" onClick={loadCards}>
            <RotateCcw className="mr-2 h-4 w-4" />
            重新开始
          </Button>
        </div>
      </div>
    );
  }

  if (completed) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6">
        <div className="rounded-full bg-green-100 p-6">
          <Trophy className="h-16 w-16 text-green-600" />
        </div>
        <h2 className="text-2xl font-bold">太棒了！</h2>
        <p className="text-muted-foreground text-center">
          {reviewedCount > 0
            ? `你已完成 ${reviewedCount} 张卡片的复习`
            : "今天没有待复习的卡片了"}
        </p>
        <div className="flex gap-3">
          <Link href="/dashboard">
            <Button variant="outline">
              <ArrowLeft className="mr-2 h-4 w-4" />
              返回仪表盘
            </Button>
          </Link>
          <Button onClick={() => { reset(); loadCards(); }}>
            <RotateCcw className="mr-2 h-4 w-4" />
            再来一轮
          </Button>
        </div>
      </div>
    );
  }

  const card = currentCards[currentIndex];
  if (!card) return null;

  const progress = ((currentIndex + 1) / currentCards.length) * 100;

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link href="/dashboard">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
        </Link>
        <span className="text-sm text-muted-foreground">
          {mode === "mix" ? "混合模式" : "复习模式"} · {currentIndex + 1} / {currentCards.length}
        </span>
      </div>

      {/* Progress */}
      <Progress value={progress} className="h-2" />

      {/* Flashcard */}
      <Flashcard
        card={card}
        showAnswer={showAnswer}
        onToggleAnswer={toggleAnswer}
        onRate={handleRate}
        preview={preview}
        forceType={forceTypeMap[card.id]}
        tagPanel={
          <CardTagManager
            cardId={card.id}
            token={token!}
            onTagsChange={(tags) => updateCurrentCard({ tags_list: tags })}
          />
        }
      />
    </div>
  );
}
