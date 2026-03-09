"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Eye, BookOpen, Lightbulb } from "lucide-react";
import { isHiddenTag, ArticleSourceLink } from "@/components/card-detail";

interface FlashcardProps {
  card: {
    id: number;
    front: string;
    back: string;
    explanation?: string;
    distractors?: string;  // JSON string: ["wrong1","wrong2","wrong3"]
    meta_info?: string;    // JSON string with extended knowledge
    source?: string;
    category_name?: string;
    tags_list?: { id: number; name: string; color: string }[];
  };
  showAnswer: boolean;
  onToggleAnswer: () => void;
  onRate?: (rating: number) => void;
  preview?: { [key: string]: string } | null;
  showRatings?: boolean;
  forceType?: "qa" | "choice";  // Override question type display regardless of distractors
  tagPanel?: React.ReactNode;  // Optional tag management panel to render inside
  readOnly?: boolean;  // If true, show answer but hide rating buttons (browsing history)
  articleMap?: Record<string, { id: number; title: string; quality_score: number; source_name: string }>;  // Pre-loaded article info keyed by source URL
}

const RATING_LABELS = [
  { value: 1, label: "忘了", shortcut: "1", className: "rating-again" },
  { value: 2, label: "困难", shortcut: "2", className: "rating-hard" },
  { value: 3, label: "记得", shortcut: "3", className: "rating-good" },
  { value: 4, label: "简单", shortcut: "4", className: "rating-easy" },
];

/** Parse JSON string safely, return fallback on error */
function parseJson<T>(str: string | undefined, fallback: T): T {
  if (!str) return fallback;
  try {
    const parsed = JSON.parse(str);
    return parsed ?? fallback;
  } catch {
    return fallback;
  }
}

export default function Flashcard({
  card,
  showAnswer,
  onToggleAnswer,
  onRate,
  preview,
  showRatings = true,
  forceType,
  tagPanel,
  readOnly = false,
  articleMap,
}: FlashcardProps) {
  const [selectedChoice, setSelectedChoice] = useState<number | null>(null);

  // Pick alternate question from meta_info for variety
  const [altQuestion, setAltQuestion] = useState<{
    question: string; answer: string; choices?: string[]; distractors?: string[];
  } | null>(null);

  // Random display type: 60% QA, 40% choice (applied per card)
  const [randomForceType, setRandomForceType] = useState<"qa" | "choice">("choice");

  // Reset when card changes & randomly pick from [front/back, ...alternates]
  React.useEffect(() => {
    setSelectedChoice(null);
    // 实词辨析 cards: always choice; others: 60% QA, 40% choice
    if (card.category_name === "实词辨析") {
      setRandomForceType("choice");
    } else {
      setRandomForceType(Math.random() < 0.6 ? "qa" : "choice");
    }

    const meta = parseJson<Record<string, any> | null>(card.meta_info, null);
    const alts = meta?.alternate_questions;
    if (alts?.length) {
      const candidates = alts.filter((q: any) => q.question && (q.answer || q.correct_answer));
      if (candidates.length) {
        // Pool: [null (= use original front/back), ...candidates]
        const pool: (any | null)[] = [null, ...candidates];
        setAltQuestion(pool[Math.floor(Math.random() * pool.length)]);
        return;
      }
    }
    setAltQuestion(null);
  }, [card.id, card.meta_info]);

  // Effective front/back (may be overridden by alternate question)
  const effectiveFront = altQuestion?.question || card.front;
  const effectiveBack = altQuestion?.answer || altQuestion?.correct_answer || card.back;

  // Parse distractors
  const distractors: string[] = React.useMemo(() => {
    if (altQuestion) {
      const altAnswer = altQuestion.answer || altQuestion.correct_answer;
      // New format: distractors stored directly
      if (altQuestion.distractors?.length) {
        return altQuestion.distractors;
      }
      // Legacy format: extract from choices by removing answer
      if (altQuestion.choices) {
        return altQuestion.choices.filter((c: string) => c !== altAnswer);
      }
    }
    return parseJson(card.distractors, []);
  }, [altQuestion, card.distractors]);

  const hasDistractors = distractors.length > 0;
  // forceType (from quiz) takes priority; otherwise use random 60:40 ratio
  const isChoice = forceType
    ? forceType === "choice"
    : (randomForceType === "choice" && hasDistractors);
  const cardTypeLabel = isChoice ? "选择题" : "问答题";
  
  // Filter out hidden tags
  const visibleTags = card.tags_list?.filter(tag => !isHiddenTag(tag.name)) || [];

  // Build shuffled choices (distractors + correct answer)
  const choices: string[] = React.useMemo(() => {
    if (!isChoice) return [];
    const opts = [...distractors, effectiveBack];
    // Deterministic shuffle — hash card.id + question text for alternate variety
    let seed = card.id;
    if (altQuestion) {
      for (let i = 0; i < altQuestion.question.length; i++) {
        seed = ((seed << 5) - seed + altQuestion.question.charCodeAt(i)) | 0;
      }
      seed = seed >>> 0;
    }
    for (let i = opts.length - 1; i > 0; i--) {
      const j = ((seed * (i + 1) * 2654435761) >>> 0) % (i + 1);
      [opts[i], opts[j]] = [opts[j], opts[i]];
    }
    return opts;
  }, [card.id, effectiveBack, distractors, isChoice, altQuestion]);

  // Parse meta_info for back-side display
  const metaInfo = React.useMemo(() => parseJson<Record<string, any> | null>(card.meta_info, null), [card.meta_info]);

  // Handle keyboard shortcuts
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        onToggleAnswer();
      }
      if (onRate && !readOnly && ["1", "2", "3", "4"].includes(e.key)) {
        onRate(parseInt(e.key));
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [showAnswer, onRate, onToggleAnswer, readOnly]);

  // Auto-show answer in readOnly mode (reviewing previously rated card)
  React.useEffect(() => {
    if (readOnly && !showAnswer) {
      onToggleAnswer();
    }
  }, [readOnly, card.id]);

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Type & category & tag badges */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        {readOnly && (
          <Badge variant="outline" className="text-xs border-green-500 text-green-600">✅ 已回答</Badge>
        )}
        {card.category_name && (
          <Badge variant="secondary">{card.category_name}</Badge>
        )}
        {card.tags_list && card.tags_list.length > 0 && card.tags_list.filter((tag) => !isHiddenTag(tag.name)).map((tag) => (
          <Badge
            key={tag.id}
            className="text-xs"
            style={{
              backgroundColor: tag.color ? `${tag.color}20` : undefined,
              color: tag.color || undefined,
              borderColor: tag.color || undefined,
            }}
            variant="outline"
          >
            🏷️ {tag.name}
          </Badge>
        ))}
      </div>

      {/* Front side */}
      <div
        className={cn(
          "rounded-xl border-2 bg-card p-8 min-h-[200px] flex flex-col justify-center cursor-pointer transition-all",
          showAnswer ? "border-primary/30" : "border-border hover:border-primary/50"
        )}
        onClick={onToggleAnswer}
      >
        <div className="text-xl font-medium text-center leading-relaxed whitespace-pre-line">
          {effectiveFront}
        </div>

        {/* Choice options */}
        {isChoice && choices.length > 0 && (
          <div className="mt-6 space-y-2">
            {choices.map((opt, i) => {
              const letter = String.fromCharCode(65 + i);
              const isCorrect = showAnswer && opt === effectiveBack;
              const isSelected = selectedChoice === i;
              const isWrong = isSelected && showAnswer && opt !== effectiveBack;
              return (
                <button
                  key={`${card.id}-${i}`}
                  className={cn(
                    "w-full text-left px-4 py-3 rounded-lg border transition-colors",
                    isCorrect
                      ? "bg-green-50 border-green-400 text-green-800 dark:bg-green-950 dark:border-green-600 dark:text-green-200"
                      : isWrong
                      ? "bg-red-50 border-red-400 text-red-800 dark:bg-red-950 dark:border-red-600 dark:text-red-200"
                      : "hover:bg-muted"
                  )}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedChoice(i);
                    if (!showAnswer) {
                      setTimeout(() => onToggleAnswer(), 100);
                    }
                  }}
                >
                  <span className="font-medium mr-2">{letter}.</span>
                  {opt}
                </button>
              );
            })}
          </div>
        )}

        {/* Reveal hint (Q&A only) */}
        {!showAnswer && !isChoice && (
          <div className="mt-6 flex items-center justify-center text-muted-foreground text-sm gap-1">
            <Eye className="h-4 w-4" />
            点击或按空格显示答案
          </div>
        )}
      </div>

      {/* ── Answer Panel ── */}
      {showAnswer && (
        <div className="mt-4 rounded-xl bg-muted/50 border p-6 space-y-4 animate-slide-up">
          {/* Correct answer */}
          <div className="bg-green-50 dark:bg-green-950/30 rounded-lg p-4">
            <div className="text-xs font-semibold text-green-700 dark:text-green-400 mb-1.5 flex items-center gap-1.5">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-green-200 dark:bg-green-800 text-[10px]">✅</span>
              正确答案
            </div>
            <div className="text-lg font-medium text-green-900 dark:text-green-100">{effectiveBack}</div>
            {/* Pinyin from meta_info (for idiom cards) — consolidated from all sources */}
            {(metaInfo?.pinyin || metaInfo?.meta_info?.pinyin || metaInfo?.facts?.pinyin) && (
              <div className="mt-1.5 text-sm tracking-wider">
                🔤 拼音：{metaInfo?.pinyin || metaInfo?.meta_info?.pinyin || metaInfo?.facts?.pinyin}
              </div>
            )}
            {metaInfo?.example_sentence && (
              <div className="mt-1.5 text-sm text-green-800/70 dark:text-green-200/70">
                📝 例句：{metaInfo.example_sentence}
              </div>
            )}
          </div>

          {/* Explanation */}
          {card.explanation && (
            <div className="bg-blue-50 dark:bg-blue-950/30 rounded-lg p-4">
              <div className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-1.5 flex items-center gap-1.5">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-200 dark:bg-blue-800 text-[10px]">📖</span>
                解析说明
              </div>
              <div className="text-sm leading-relaxed whitespace-pre-line text-blue-900 dark:text-blue-100">{card.explanation}</div>
            </div>
          )}

          {/* Extended knowledge from meta_info */}
          {metaInfo && <MetaInfoPanel meta={metaInfo} />}

          {/* Article Source Link */}
          {card.source && <ArticleSourceLink sourceUrl={card.source} preloaded={articleMap?.[card.source]} />}
        </div>
      )}

      {/* Inline tag panel (shown when answer is visible) */}
      {showAnswer && tagPanel}

      {/* Rating buttons - fixed at bottom on all screen sizes */}
      {showRatings && onRate && (
        <div className="mt-6 fixed bottom-0 md:bottom-0 left-0 md:left-64 right-0 bg-background/95 backdrop-blur-sm border-t p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] z-[55] mobile-rating-bottom">
          <div className="grid grid-cols-4 gap-2 max-w-2xl mx-auto">
            {RATING_LABELS.map((r) => (
              <Button
                key={r.value}
                className={cn("flex-col gap-1 h-auto py-3", r.className)}
                onClick={() => {
                  onRate(r.value);
                }}
              >
                <span className="text-base font-bold">{r.label}</span>
                {preview && showAnswer && (
                  <span className="text-[10px] opacity-80">
                    {preview[String(r.value)] || ""}
                  </span>
                )}
                <kbd className="text-[10px] opacity-60 bg-black/10 px-1 rounded">
                  {r.shortcut}
                </kbd>
              </Button>
            ))}
          </div>
        </div>
      )}
      {/* Spacer for fixed bottom bar */}
      {showRatings && onRate && (
        <div className="h-28" />
      )}
    </div>
  );
}

/** Friendly label mapping for meta_info facts keys */
const FACTS_LABEL_MAP: Record<string, { label: string; icon: string; color: string }> = {
  // ─── 通用 ───
  example_sentence: { label: "例句",     icon: "📝", color: "text-teal-700 dark:text-teal-400" },
  subject_idiom:   { label: "相关成语", icon: "📝", color: "text-purple-700 dark:text-purple-400" },
  subject:         { label: "主题",     icon: "📌", color: "text-blue-700 dark:text-blue-400" },
  meaning:         { label: "含义",     icon: "💡", color: "text-amber-700 dark:text-amber-400" },
  correct_option:  { label: "正确选项", icon: "✅", color: "text-green-700 dark:text-green-400" },
  common_error:    { label: "常见错误", icon: "❌", color: "text-red-700 dark:text-red-400" },
  origin:          { label: "出处典故", icon: "📖", color: "text-indigo-700 dark:text-indigo-400" },
  formal_usage:    { label: "规范用法", icon: "📋", color: "text-teal-700 dark:text-teal-400" },
  key_distinction: { label: "关键区别", icon: "🔑", color: "text-orange-700 dark:text-orange-400" },
  example:         { label: "示例",     icon: "📝", color: "text-sky-700 dark:text-sky-400" },
  note:            { label: "注意",     icon: "⚡", color: "text-yellow-700 dark:text-yellow-400" },
  source:          { label: "来源",     icon: "📚", color: "text-slate-700 dark:text-slate-400" },
  date:            { label: "日期",     icon: "📅", color: "text-gray-700 dark:text-gray-400" },
  category:        { label: "类别",     icon: "🏷️",  color: "text-cyan-700 dark:text-cyan-400" },
  context:         { label: "适用场景", icon: "🔍", color: "text-violet-700 dark:text-violet-400" },
  usage:           { label: "用法",     icon: "✏️",  color: "text-emerald-700 dark:text-emerald-400" },
  // ─── 成语 ───
  emotion:         { label: "感情色彩", icon: "🎭", color: "text-pink-700 dark:text-pink-400" },
  common_misuse:   { label: "易错用法", icon: "⚠️",  color: "text-red-700 dark:text-red-400" },
  // ─── 实词辨析 ───
  word_distinction:{ label: "词语辨析", icon: "🔑", color: "text-orange-700 dark:text-orange-400" },
  wrong_reason:    { label: "误选原因", icon: "❌", color: "text-red-700 dark:text-red-400" },
  // ─── 时政 ───
  policy_background:{ label: "政策背景", icon: "🏛️", color: "text-blue-700 dark:text-blue-400" },
  significance:    { label: "现实意义", icon: "🎯", color: "text-emerald-700 dark:text-emerald-400" },
  exam_angle:      { label: "考试角度", icon: "📐", color: "text-amber-700 dark:text-amber-400" },
  // ─── 常识/政治理论 ───
  misconception:   { label: "常见误区", icon: "⚠️",  color: "text-red-700 dark:text-red-400" },
  classic_statement:{ label: "经典表述", icon: "💬", color: "text-indigo-700 dark:text-indigo-400" },
  // ─── 历史 ───
  historical_context:{ label: "历史背景", icon: "🏛️", color: "text-amber-700 dark:text-amber-400" },
  // ─── 逻辑/数量 ───
  solution_steps:  { label: "解题步骤", icon: "🔢", color: "text-blue-700 dark:text-blue-400" },
  common_trap:     { label: "常见陷阱", icon: "🪤", color: "text-red-700 dark:text-red-400" },
  // ─── 申论 ───
  usage_scenario:  { label: "使用场景", icon: "📋", color: "text-teal-700 dark:text-teal-400" },
  writing_framework:{ label: "写作框架", icon: "🏗️", color: "text-violet-700 dark:text-violet-400" },
  supporting_data: { label: "支撑数据", icon: "📊", color: "text-sky-700 dark:text-sky-400" },
  // ─── 古诗词 ───
  full_poem:       { label: "全诗",     icon: "📜", color: "text-amber-700 dark:text-amber-400" },
  appreciation:    { label: "赏析",     icon: "🌸", color: "text-pink-700 dark:text-pink-400" },
  writing_note:    { label: "公文要点", icon: "📝", color: "text-teal-700 dark:text-teal-400" },
  // ─── 其他元信息 ───
  speaker:         { label: "出处/人物", icon: "👤", color: "text-slate-700 dark:text-slate-400" },
  topic:           { label: "话题",     icon: "📌", color: "text-blue-700 dark:text-blue-400" },
  law_name:        { label: "法律名称", icon: "⚖️",  color: "text-indigo-700 dark:text-indigo-400" },
  article:         { label: "条款",     icon: "📜", color: "text-slate-700 dark:text-slate-400" },
  author:          { label: "作者",     icon: "✍️",  color: "text-amber-700 dark:text-amber-400" },
  dynasty:         { label: "朝代",     icon: "🏯", color: "text-orange-700 dark:text-orange-400" },
  work:            { label: "作品",     icon: "📖", color: "text-indigo-700 dark:text-indigo-400" },
  period:          { label: "时期",     icon: "📅", color: "text-gray-700 dark:text-gray-400" },
  event:           { label: "事件",     icon: "📰", color: "text-blue-700 dark:text-blue-400" },
};

function getFactLabel(key: string): { label: string; icon: string; color: string } {
  if (FACTS_LABEL_MAP[key]) return FACTS_LABEL_MAP[key];
  const lower = key.toLowerCase();
  if (lower.includes("idiom") || lower.includes("成语")) return { label: "成语", icon: "📝", color: "text-purple-700 dark:text-purple-400" };
  if (lower.includes("origin") || lower.includes("出处")) return { label: "出处", icon: "📖", color: "text-indigo-700 dark:text-indigo-400" };
  if (lower.includes("misuse") || lower.includes("误")) return { label: "常见误用", icon: "⚠️", color: "text-red-700 dark:text-red-400" };
  if (lower.includes("meaning") || lower.includes("含义")) return { label: "含义", icon: "💡", color: "text-amber-700 dark:text-amber-400" };
  return { label: key.replace(/_/g, " "), icon: "📎", color: "text-muted-foreground" };
}

/** Renders extended knowledge from meta_info on the back side */
function MetaInfoPanel({ meta }: { meta: Record<string, any> }) {
  const knowledge = meta.knowledge as Record<string, any> | undefined;
  const examFocus = meta.exam_focus as Record<string, any> | undefined;
  const facts = meta.facts as Record<string, string> | undefined;

  const hasKnowledge = knowledge && Object.values(knowledge).some((v) =>
    Array.isArray(v) ? v.length > 0 : !!v
  );
  const hasFacts = facts && Object.keys(facts).filter(k => k !== "pinyin").length > 0;

  if (!hasKnowledge && !hasFacts && !examFocus) return null;

  return (
    <div className="border-t pt-3 space-y-3">
      <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
        <BookOpen className="h-3 w-3" />
        拓展知识
      </div>

      {/* Knowledge section */}
      {hasKnowledge && (
        <div className="bg-purple-50/50 dark:bg-purple-950/20 rounded-lg p-3 space-y-1.5">
          <div className="text-xs font-semibold text-purple-700 dark:text-purple-400 mb-1">🧠 知识拓展</div>
          <div className="grid gap-1 text-sm">
            <KnowledgeRow label="🔑 核心考点" value={knowledge!.key_points} />
            <KnowledgeRow label="📝 金句" value={knowledge!.golden_quotes} />
            <KnowledgeRow label="📋 规范用语" value={knowledge!.formal_terms} />
            <KnowledgeRow label="🔗 相关知识" value={knowledge!.related} />
            <KnowledgeRow label="≈ 近义词" value={knowledge!.synonyms} />
            <KnowledgeRow label="↔ 反义词" value={knowledge!.antonyms} />
            {knowledge!.essay_material && (
              <div>
                <span className="text-muted-foreground">✍️ 申论素材：</span>
                <span>{String(knowledge!.essay_material)}</span>
              </div>
            )}
            {knowledge!.memory_tips && (
              <div>
                <span className="text-muted-foreground">💡 记忆技巧：</span>
                <span>{String(knowledge!.memory_tips)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Facts section — with friendly labels, icons, colors (pinyin shown separately) */}
      {hasFacts && (
        <div className="bg-amber-50/50 dark:bg-amber-950/20 rounded-lg p-3">
          <div className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-2">📋 关键信息</div>
          <div className="grid gap-1.5 text-sm">
            {Object.entries(facts!).filter(([k]) => k !== "pinyin").map(([k, v]) => {
              const { label, icon, color } = getFactLabel(k);
              return (
                <div key={k} className="flex items-start gap-1.5">
                  <span className={cn("shrink-0 font-medium", color)}>
                    {icon} {label}：
                  </span>
                  <span className="text-foreground">{v}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Exam focus badges */}
      {examFocus && (
        <div className="flex flex-wrap gap-2">
          {!!examFocus.difficulty && (
            <Badge variant="secondary" className="text-xs">
              {examFocus.difficulty === "easy" ? "🟢 简单" : examFocus.difficulty === "hard" ? "🔴 困难" : "🟡 中等"}
            </Badge>
          )}
          {!!examFocus.frequency && (
            <Badge variant="secondary" className="text-xs">
              {examFocus.frequency === "high" ? "🔥 高频考点" : examFocus.frequency === "low" ? "⬇️ 低频" : "➡️ 中频"}
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}

/** A single row of knowledge items (array or string) */
function KnowledgeRow({ label, value }: { label: string; value: any }) {
  if (!value) return null;
  const items = Array.isArray(value) ? value : [value];
  if (items.length === 0) return null;
  return (
    <div>
      <span className="text-muted-foreground">{label}：</span>
      <span>{items.join("、")}</span>
    </div>
  );
}
