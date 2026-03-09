"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useAuthStore, useStudyStore } from "@/lib/store";
import { review, auth, tags as tagsApi } from "@/lib/api";
import Flashcard from "@/components/flashcard";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ArrowLeft, ArrowRight, ChevronLeft, ChevronRight, Trophy, RotateCcw, PlayCircle } from "lucide-react";
import Link from "next/link";
import { CardTagManager } from "@/components/card-detail";
import { useSwipe } from "@/hooks/use-swipe";

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
    reviewedIndices,
    setCards,
    initSession,
    nextCard,
    prevCard,
    markReviewed,
    toggleAnswer,
    updateCurrentCard,
    reset,
  } = useStudyStore();

  const [loading, setLoading] = useState(true);
  const [completed, setCompleted] = useState(false);
  const [reviewedCount, setReviewedCount] = useState(0);
  const [pendingSession, setPendingSession] = useState<any>(null);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [cardStartTime, setCardStartTime] = useState<number>(Date.now());

  // Buffered answers for batch submission
  const [bufferedAnswers, setBufferedAnswers] = useState<{ card_id: number; rating: number; review_duration_ms?: number }[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  // All tags cache — fetched once at page load
  const [allTagsCache, setAllTagsCache] = useState<any[]>([]);

  // Question type config (persisted on user profile)
  const [showTypeConfig, setShowTypeConfig] = useState(false);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [questionMode, setQuestionMode] = useState<"all_choice" | "all_qa" | "custom">("custom");
  const [customRatio, setCustomRatio] = useState<number>(60);

  // Q&A/choice ratio: pre-compute for each card
  const [forceTypeMap, setForceTypeMap] = useState<Record<number, "qa" | "choice">>({});

  // Compute force types based on user's question mode setting
  const computeForceTypes = useCallback((cards: any[], qMode?: string, qRatio?: number) => {
    const map: Record<number, "qa" | "choice"> = {};
    const mode_ = qMode || questionMode;
    const ratio = (qRatio ?? customRatio) / 100;
    cards.forEach((c) => {
      if (c.category_name === "实词辨析") {
        map[c.id] = "choice";
      } else if (mode_ === "all_qa") {
        map[c.id] = "qa";
      } else if (mode_ === "all_choice") {
        map[c.id] = "choice";
      } else {
        map[c.id] = Math.random() < ratio ? "qa" : "choice";
      }
    });
    setForceTypeMap(map);
  }, [questionMode, customRatio]);


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
      sessionParams.question_mode = questionMode;
      sessionParams.custom_ratio = customRatio;
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

  // Resume an unfinished session (with history of reviewed cards)
  const _resumeWithHistory = useCallback(async (sess: any) => {
    setSessionId(sess.id);
    if (sess.question_mode) setQuestionMode(sess.question_mode);
    if (sess.custom_ratio != null) setCustomRatio(sess.custom_ratio);

    const remaining: number[] = JSON.parse(sess.remaining_card_ids || "[]");
    const allIds: number[] = JSON.parse(sess.all_card_ids || "[]");
    const remainingSet = new Set(remaining);

    // If we have the full card list, fetch all cards for history navigation
    if (allIds.length > 0) {
      const data = await review.getDue({ card_ids: allIds }, token!);
      const allCards: any[] = data.cards || [];
      if (allCards.length > 0) {
        // Sort: reviewed cards first (in original order), then remaining
        const reviewedCards = allIds
          .filter((id) => !remainingSet.has(id))
          .map((id) => allCards.find((c: any) => c.id === id))
          .filter(Boolean);
        const remainingCards = allIds
          .filter((id) => remainingSet.has(id))
          .map((id) => allCards.find((c: any) => c.id === id))
          .filter(Boolean);
        const orderedCards = [...reviewedCards, ...remainingCards];

        // Build reviewed indices set (first N cards are already reviewed)
        const reviewedIdxSet = new Set<number>();
        for (let i = 0; i < reviewedCards.length; i++) reviewedIdxSet.add(i);

        initSession(orderedCards, reviewedCards.length, reviewedIdxSet);
        computeForceTypes(orderedCards, sess.question_mode, sess.custom_ratio);
        setReviewedCount(sess.cards_reviewed || 0);
        return true;
      }
    }

    // Fallback: old session without all_card_ids — load remaining only
    const data = await review.getDue({ limit: 200 }, token!);
    const resumeCards = (data.cards || []).filter((c: any) => remainingSet.has(c.id));
    if (resumeCards.length > 0) {
      setCards(resumeCards);
      computeForceTypes(resumeCards, sess.question_mode, sess.custom_ratio);
      setReviewedCount(sess.cards_reviewed || 0);
      return true;
    }
    return false;
  }, [token, initSession, setCards, computeForceTypes]);

  const resumeSession = useCallback(async () => {
    if (!token || !pendingSession) return;
    setLoading(true);
    setPendingSession(null);
    try {
      const ok = await _resumeWithHistory(pendingSession);
      if (!ok) await loadCards();
    } finally {
      setLoading(false);
    }
  }, [token, pendingSession, _resumeWithHistory, loadCards]);

  // Save settings to user profile and start studying
  const startWithConfig = useCallback(async () => {
    if (token) {
      try {
        const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
        await fetch(`${API_BASE}/api/auth/me`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
          body: JSON.stringify({ study_question_mode: questionMode, study_custom_ratio: customRatio }),
        });
      } catch { /* non-critical */ }
    }
    setShowTypeConfig(false);
    await loadCards();
  }, [questionMode, customRatio, loadCards, token]);

  useEffect(() => {
    const init = async () => {
      const wantsResume = params.get("resume") === "1";

      // Load user study preferences and all tags in parallel
      if (token && !settingsLoaded) {
        try {
          const [me, tagsList] = await Promise.all([
            auth.me(token),
            tagsApi.list(token).catch(() => []),
          ]);
          if (me.study_question_mode) setQuestionMode(me.study_question_mode);
          if (me.study_custom_ratio != null) setCustomRatio(me.study_custom_ratio);
          setSettingsLoaded(true);
          setAllTagsCache(tagsList);
        } catch { /* use defaults */ }
      }

      if (wantsResume) {
        // Coming from dashboard "继续学习" — auto-resume without showing prompt
        if (!token) return;
        try {
          const session = await review.getActiveSession(token);
          if (session && !session.is_completed && session.mode !== "quiz") {
            const remaining = JSON.parse(session.remaining_card_ids || "[]");
            if (remaining.length > 0) {
              // Auto-resume with history
              const ok = await _resumeWithHistory(session);
              if (ok) {
                setLoading(false);
                return;
              }
            }
          }
        } catch {
          // Fall through to config screen
        }
      }
      // Show question type config screen before starting
      setShowTypeConfig(true);
      setLoading(false);
    };
    init();
    return () => reset();
  }, []);

  // Auto-flush when all cards completed
  const completedFlushRef = useRef(false);
  useEffect(() => {
    if (completed && bufferedAnswers.length > 0 && !completedFlushRef.current) {
      completedFlushRef.current = true;
      flushAnswers();
    }
  }, [completed, bufferedAnswers.length]);

  // Reset timer when card changes
  useEffect(() => {
    if (!currentCards[currentIndex]) return;
    setCardStartTime(Date.now());
  }, [currentCards, currentIndex]);

  // --- Auto-save flag to prevent double-fire ---
  const autoSaveFiredRef = useRef(false);

  // Flush buffered answers to server in one batch
  const flushAnswers = useCallback(async (answers?: typeof bufferedAnswers) => {
    const toFlush = answers || bufferedAnswers;
    if (toFlush.length === 0 || !token) return;
    autoSaveFiredRef.current = true; // Prevent auto-save from duplicating
    setIsSaving(true);
    try {
      await review.batchAnswer(toFlush, token, sessionId);
    } catch (err) {
      console.error("Batch submit failed, falling back to single:", err);
      for (const a of toFlush) {
        try { await review.answer(a, token); } catch {}
      }
    }
    if (!answers) setBufferedAnswers([]);
    setIsSaving(false);
    autoSaveFiredRef.current = false; // Allow future auto-saves for new answers
  }, [bufferedAnswers, token, sessionId]);

  // --- Auto-save on page leave ---
  const autoSaveStudyRef = useRef<() => void>();
  autoSaveStudyRef.current = () => {
    if (autoSaveFiredRef.current) return;
    if (!token || bufferedAnswers.length === 0) return;
    autoSaveFiredRef.current = true;
    // Use fetch with keepalive for reliability during page unload
    fetch("/api/review/batch-answer", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ answers: bufferedAnswers, session_id: sessionId }),
      keepalive: true,
    }).catch(() => {});
  };

  useEffect(() => {
    const handleBeforeUnload = () => autoSaveStudyRef.current?.();

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      // Save on unmount (SPA route change)
      autoSaveStudyRef.current?.();
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, []);

  const handleRate = (rating: number) => {
    const card = currentCards[currentIndex];
    const durationMs = Math.min(Date.now() - cardStartTime, 600000); // cap at 10 min
    const wasAlreadyReviewed = reviewedIndices.has(currentIndex);

    // Pure local operation — no network calls
    const answerData = { card_id: card.id, rating, review_duration_ms: durationMs };
    setBufferedAnswers(prev => {
      const filtered = prev.filter(a => a.card_id !== card.id);
      return [...filtered, answerData];
    });

    markReviewed(currentIndex);

    if (!wasAlreadyReviewed) {
      setReviewedCount((c) => c + 1);

      if (currentIndex + 1 < currentCards.length) {
        nextCard();
      } else {
        setCompleted(true);
      }
    }
    // Re-rating: stay on current card
  };

  // Swipe hook MUST be called unconditionally (Rules of Hooks — before any early return)
  const swipeRef = useSwipe<HTMLDivElement>({
    onSwipeLeft: () => {
      const reviewed = reviewedIndices.has(currentIndex);
      if (currentIndex < currentCards.length - 1 && reviewed) nextCard();
    },
    onSwipeRight: () => { if (currentIndex > 0) prevCard(); },
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  // Question type config screen
  if (showTypeConfig) {
    return (
      <div className="max-w-md mx-auto flex flex-col items-center justify-center min-h-[60vh] gap-6 px-4">
        <div className="rounded-full bg-blue-100 dark:bg-blue-950 p-6">
          <PlayCircle className="h-12 w-12 text-blue-600" />
        </div>
        <h2 className="text-2xl font-bold">出题设置</h2>
        <p className="text-sm text-muted-foreground text-center">
          {mode === "mix" ? "混合模式" : "复习模式"} · 选择题目类型
        </p>

        <div className="w-full space-y-2">
          {([
            { value: "all_qa" as const, label: "全问答题", desc: "所有题目以问答形式出题" },
            { value: "all_choice" as const, label: "全选择题", desc: "所有题目以选择题形式出题" },
            { value: "custom" as const, label: "指定比例", desc: "自定义问答题和选择题的比例" },
          ]).map(({ value, label, desc }) => (
            <button
              key={value}
              className={`w-full p-3 rounded-lg border text-left transition-colors ${
                questionMode === value
                  ? "border-blue-500 bg-blue-50 dark:bg-blue-950/50"
                  : "border-border hover:bg-muted/50"
              }`}
              onClick={() => setQuestionMode(value)}
            >
              <div className="flex items-center gap-3">
                <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                  questionMode === value ? "border-blue-500" : "border-muted-foreground/30"
                }`}>
                  {questionMode === value && (
                    <div className="w-2 h-2 rounded-full bg-blue-500" />
                  )}
                </div>
                <div>
                  <div className="font-medium text-sm">{label}</div>
                  <div className="text-xs text-muted-foreground">{desc}</div>
                </div>
              </div>
            </button>
          ))}

          {questionMode === "custom" && (
            <div className="mt-3 p-3 rounded-lg bg-muted/50 space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span>问答题 <strong>{customRatio}%</strong></span>
                <span>选择题 <strong>{100 - customRatio}%</strong></span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                step={10}
                value={customRatio}
                onChange={(e) => setCustomRatio(parseInt(e.target.value))}
                className="w-full accent-blue-500"
              />
            </div>
          )}
        </div>

        <Button
          className="w-full"
          size="lg"
          onClick={startWithConfig}
        >
          <PlayCircle className="mr-2 h-4 w-4" />
          开始{mode === "mix" ? "练习" : "复习"}
        </Button>
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
  const isCurrentReviewed = reviewedIndices.has(currentIndex);
  const canGoPrev = currentIndex > 0;
  const canGoNext = currentIndex < currentCards.length - 1 && isCurrentReviewed;

  const handlePrev = () => { if (canGoPrev) prevCard(); };
  const handleNext = () => { if (canGoNext) nextCard(); };

  return (
    <div className="max-w-2xl mx-auto space-y-4" ref={swipeRef}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <Link href="/dashboard">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
        </Link>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => flushAnswers()}
            disabled={isSaving || bufferedAnswers.length === 0}
            variant="outline"
            size="lg"
            className="text-base h-10 px-5 font-medium bg-green-50 hover:bg-green-100 text-green-700 border-green-300 dark:bg-green-950/30 dark:hover:bg-green-950/50 dark:text-green-400 dark:border-green-800"
          >
            {isSaving ? "保存中..." : `💾 暂存 (${reviewedCount}/${currentCards.length})`}
          </Button>
          {isCurrentReviewed && (
            <span className="text-xs text-green-600 bg-green-50 dark:bg-green-950/30 px-2 py-0.5 rounded-full">
              ✅ 已评分
            </span>
          )}
          <span className="text-sm text-muted-foreground">
            {mode === "mix" ? "混合模式" : "复习模式"} · {currentIndex + 1} / {currentCards.length}
          </span>
        </div>
      </div>

      {/* Progress */}
      <Progress value={progress} className="h-2" />

      {/* Prev / Next navigation */}
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={handlePrev} disabled={!canGoPrev}>
          <ChevronLeft className="mr-1 h-4 w-4" />
          上一题
        </Button>
        <Button variant="ghost" size="sm" onClick={handleNext} disabled={!canGoNext}>
          下一题
          <ChevronRight className="ml-1 h-4 w-4" />
        </Button>
      </div>

      {/* Flashcard */}
      <Flashcard
        card={card}
        showAnswer={showAnswer}
        onToggleAnswer={toggleAnswer}
        onRate={handleRate}
        preview={card.scheduling_preview}
        forceType={forceTypeMap[card.id]}
        articleMap={card.source && card.article_id ? { [card.source]: { id: card.article_id, title: card.article_title, quality_score: card.article_quality_score, source_name: card.article_source_name } } : undefined}
        tagPanel={
          <CardTagManager
            cardId={card.id}
            token={token!}
            onTagsChange={(tags) => updateCurrentCard({ tags_list: tags })}
            initialAllTags={allTagsCache.length > 0 ? allTagsCache : undefined}
            initialCardTags={card.tags_list || []}
          />
        }
      />
    </div>
  );
}
