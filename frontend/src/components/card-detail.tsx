"use client";

import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { tags as tagsApi, reading } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { HighlightText } from "@/components/highlight-text";
import { ExternalLink, BookOpen } from "lucide-react";

/* ── Shared utilities for card display ── */

/** Map English knowledge_type to Chinese */
const KNOWLEDGE_TYPE_MAP: Record<string, string> = {
  general: "综合", politics: "政治", history: "历史", economics: "经济",
  law: "法律", culture: "文化", science: "科学", geography: "地理",
  philosophy: "哲学", literature: "文学", art: "艺术", technology: "科技",
  management: "管理", military: "军事", education: "教育", society: "社会",
  environment: "环境", sports: "体育", health: "健康", language: "语言",
  logic: "逻辑", math: "数学", chinese: "语文", english: "英语",
  idiom: "成语",
};

export function knowledgeTypeLabel(raw: string): string {
  return KNOWLEDGE_TYPE_MAP[raw.toLowerCase().trim()] || raw;
}

/** FSRS state label with icon */
export function fsrsStateLabel(state: number): { text: string; className: string } {
  switch (state) {
    case 0: return { text: "🆕 新卡", className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" };
    case 1: return { text: "📖 学习中", className: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" };
    case 2: return { text: "✅ 复习", className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" };
    case 3: return { text: "🔄 重学", className: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" };
    default: return { text: "🆕 新卡", className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" };
  }
}

/** Parse JSON string safely */
export function parseJson<T>(str: string | undefined | null, fallback: T): T {
  if (!str) return fallback;
  try { return JSON.parse(str) ?? fallback; } catch { return fallback; }
}

/** Friendly label mapping for meta_info facts keys */
const FACTS_LABELS: Record<string, { label: string; icon: string }> = {
  // ─── 通用 ───
  example_sentence: { label: "例句", icon: "📝" },
  subject_idiom: { label: "相关成语", icon: "📝" },
  subject: { label: "主题", icon: "📌" },
  meaning: { label: "含义", icon: "💡" },
  correct_option: { label: "正确选项", icon: "✅" },
  common_error: { label: "常见错误", icon: "❌" },
  origin: { label: "出处典故", icon: "📖" },
  formal_usage: { label: "规范用法", icon: "📋" },
  key_distinction: { label: "关键区别", icon: "🔑" },
  example: { label: "示例", icon: "📝" },
  note: { label: "注意", icon: "⚡" },
  source: { label: "来源", icon: "📚" },
  date: { label: "日期", icon: "📅" },
  category: { label: "类别", icon: "🏷️" },
  context: { label: "适用场景", icon: "📋" },
  usage: { label: "用法", icon: "✏️" },
  // ─── 成语 ───
  emotion: { label: "感情色彩", icon: "🎭" },
  common_misuse: { label: "易错用法", icon: "⚠️" },
  // ─── 实词辨析 ───
  word_distinction: { label: "词语辨析", icon: "🔑" },
  wrong_reason: { label: "误选原因", icon: "❌" },
  // ─── 时政 ───
  policy_background: { label: "政策背景", icon: "🏛️" },
  significance: { label: "现实意义", icon: "🎯" },
  exam_angle: { label: "考试角度", icon: "📐" },
  // ─── 常识/政治理论 ───
  misconception: { label: "常见误区", icon: "⚠️" },
  classic_statement: { label: "经典表述", icon: "💬" },
  // ─── 历史 ───
  historical_context: { label: "历史背景", icon: "🏛️" },
  // ─── 逻辑/数量 ───
  solution_steps: { label: "解题步骤", icon: "🔢" },
  common_trap: { label: "常见陷阱", icon: "🪤" },
  // ─── 申论 ───
  usage_scenario: { label: "使用场景", icon: "📋" },
  writing_framework: { label: "写作框架", icon: "🏗️" },
  supporting_data: { label: "支撑数据", icon: "📊" },
  // ─── 古诗词 ───
  full_poem: { label: "全诗", icon: "📜" },
  appreciation: { label: "赏析", icon: "🌸" },
  writing_note: { label: "公文要点", icon: "📝" },
  // ─── 其他元信息 ───
  speaker: { label: "出处/人物", icon: "👤" },
  topic: { label: "话题", icon: "📌" },
  law_name: { label: "法律名称", icon: "⚖️" },
  article: { label: "条款", icon: "📜" },
  author: { label: "作者", icon: "✍️" },
  dynasty: { label: "朝代", icon: "🏯" },
  work: { label: "作品", icon: "📖" },
  period: { label: "时期", icon: "📅" },
  event: { label: "事件", icon: "📰" },
};

function getFriendlyLabel(key: string): { label: string; icon: string } {
  if (FACTS_LABELS[key]) return FACTS_LABELS[key];
  const lower = key.toLowerCase();
  if (lower.includes("idiom") || lower.includes("成语")) return { label: "成语", icon: "📝" };
  if (lower.includes("origin") || lower.includes("出处")) return { label: "出处", icon: "📖" };
  if (lower.includes("misuse") || lower.includes("误")) return { label: "常见误用", icon: "⚠️" };
  if (lower.includes("meaning") || lower.includes("含义")) return { label: "含义", icon: "💡" };
  return { label: key.replace(/_/g, " "), icon: "📎" };
}

function KnRow({ icon, label, value }: { icon: string; label: string; value: unknown }) {
  if (!value) return null;
  const items = Array.isArray(value) ? value.map(String) : [String(value)];
  if (items.length === 0) return null;
  return (
    <div><span className="text-muted-foreground">{icon} {label}：</span>{items.join("、")}</div>
  );
}

/* ── Tags to hide from header badges (low-value / redundant tags) ── */
const HIDDEN_TAG_PATTERNS = [
  /^选择题$/i, /^问答题$/i, /^qa$/i, /^choice$/i, /^multiple.choice$/i,
  /^简单$/i, /^中等$/i, /^困难$/i, /^easy$/i, /^medium$/i, /^hard$/i,
  /^高频$/i, /^中频$/i, /^低频$/i, /^high$/i, /^low$/i,
  /^idiom$/i, /^成语$/i,
  /^ai$/i, /^ai.generated$/i,
  /^new$/i, /^review$/i, /^learning$/i, /^relearning$/i,
  /^general$/i, /^综合$/i,
];

export function isHiddenTag(name: string): boolean {
  const trimmed = name.trim();
  return HIDDEN_TAG_PATTERNS.some((p) => p.test(trimmed));
}

/* ── Card Header Badges ── */
export function CardHeaderBadges({ card, highlightQuery }: { card: any; highlightQuery?: string }) {
  const meta = parseJson<Record<string, any> | null>(card.meta_info, null);

  // Filter tags_list to remove noisy tags
  const visibleTags = (card.tags_list || []).filter((tag: any) => !isHiddenTag(tag.name));

  return (
    <div className="flex items-center gap-2 mb-1 flex-wrap">
      <Badge
        variant="secondary"
        className={`text-xs ${fsrsStateLabel(card.state).className}`}
      >
        {fsrsStateLabel(card.state).text}
      </Badge>
      {card.is_suspended && (
        <Badge variant="secondary" className="text-xs bg-gray-200">已暂停</Badge>
      )}
      {card.is_ai_generated && (
        <Badge variant="secondary" className="text-xs bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200">🤖 AI</Badge>
      )}
      {visibleTags.length > 0 && visibleTags.map((tag: any) => (
        <Badge
          key={tag.id}
          className="text-xs"
          variant="outline"
          style={{
            backgroundColor: tag.color ? `${tag.color}20` : undefined,
            color: tag.color || undefined,
            borderColor: tag.color || undefined,
          }}
        >
          🏷️ {tag.name}
        </Badge>
      ))}
    </div>
  );
}

/* ── Article Source Link (lazy-loaded from card.source URL) ── */
export function ArticleSourceLink({ sourceUrl }: { sourceUrl: string }) {
  const { token } = useAuthStore();
  const [article, setArticle] = useState<{ id: number; title: string; quality_score: number; source_name: string } | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!token || !sourceUrl) return;
    let cancelled = false;
    reading.list({ source_url: sourceUrl, page_size: 1 }, token)
      .then((res) => {
        if (!cancelled && res.items && res.items.length > 0) {
          const item = res.items[0];
          setArticle({ id: item.id, title: item.title, quality_score: item.quality_score, source_name: item.source_name || "" });
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, [sourceUrl, token]);

  if (!loaded || !article) return null;

  const parts: string[] = [article.title];
  if (article.quality_score > 0) parts.push(`${article.quality_score}分`);
  if (article.source_name) parts.push(article.source_name);
  const label = parts[0] + (parts.length > 1 ? `（${parts.slice(1).join(" · ")}）` : "");

  return (
    <div className="bg-sky-50 dark:bg-sky-950/30 rounded-lg p-3">
      <div className="text-xs font-semibold text-sky-700 dark:text-sky-400 mb-1 flex items-center gap-1">
        <BookOpen className="h-3.5 w-3.5" /> 来源文章
      </div>
      <a
        href={`/reading?article_id=${article.id}`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-sm text-sky-600 dark:text-sky-400 hover:underline inline-flex items-center gap-1"
      >
        📄 {label}
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
  );
}

/* ── Card Detail Panel (full back + explanation + knowledge etc.) ── */
export function CardDetailPanel({ card, searchQuery }: { card: any; searchQuery?: string }) {
  const distractors: string[] = parseJson(card.distractors, []);
  const metaInfo = parseJson<Record<string, any> | null>(card.meta_info, null);
  const knowledge = metaInfo?.knowledge as Record<string, any> | undefined;
  const examFocus = metaInfo?.exam_focus as Record<string, any> | undefined;
  const facts = metaInfo?.facts as Record<string, string> | undefined;
  const altQuestions = metaInfo?.alternate_questions as any[] | undefined;

  // Extract pinyin from multiple possible locations
  const pinyin = metaInfo?.pinyin
    || metaInfo?.meta_info?.pinyin
    || (facts as any)?.pinyin
    || null;
  const isIdiom = metaInfo?.knowledge_type === "idiom";

  return (
    <div className="space-y-4 pt-3 border-t">
      {/* Answer */}
      <div className="bg-green-50 dark:bg-green-950/30 rounded-lg p-3">
        <div className="text-xs font-semibold text-green-700 dark:text-green-400 mb-1 flex items-center gap-1">
          ✅ 答案
        </div>
        <div className="text-sm font-medium">{searchQuery ? <HighlightText text={card.back} query={searchQuery} /> : card.back}</div>
        {metaInfo?.example_sentence && (
          <div className="mt-1 text-xs text-green-800/70 dark:text-green-200/70">
            📝 例句：{metaInfo.example_sentence}
          </div>
        )}
      </div>

      {/* Pinyin — dedicated section for idiom cards or whenever pinyin exists */}
      {pinyin && (
        <div className="bg-teal-50 dark:bg-teal-950/30 rounded-lg p-3">
          <div className="text-xs font-semibold text-teal-700 dark:text-teal-400 mb-1 flex items-center gap-1">
            🔤 拼音
          </div>
          <div className="text-sm font-medium tracking-wider">{pinyin}</div>
        </div>
      )}

      {/* Distractors */}
      {distractors.length > 0 && (
        <div className="bg-red-50 dark:bg-red-950/20 rounded-lg p-3">
          <div className="text-xs font-semibold text-red-700 dark:text-red-400 mb-1.5 flex items-center gap-1">
            ❌ 干扰项
          </div>
          <div className="flex flex-wrap gap-1.5">
            {distractors.map((d, i) => (
              <Badge key={i} variant="outline" className="text-xs bg-white dark:bg-background">
                {d}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Explanation */}
      {card.explanation && (
        <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-3">
          <div className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-1 flex items-center gap-1">
            📖 解析
          </div>
          <div className="text-sm leading-relaxed whitespace-pre-line">{searchQuery ? <HighlightText text={card.explanation} query={searchQuery} /> : card.explanation}</div>
        </div>
      )}

      {/* Knowledge */}
      {knowledge && Object.values(knowledge).some((v) => Array.isArray(v) ? v.length > 0 : !!v) && (
        <div className="bg-purple-50 dark:bg-purple-950/20 rounded-lg p-3 space-y-1.5">
          <div className="text-xs font-semibold text-purple-700 dark:text-purple-400 flex items-center gap-1">
            🧠 拓展知识
          </div>
          <div className="grid gap-1 text-sm">
            <KnRow icon="🔑" label="核心考点" value={knowledge.key_points} />
            <KnRow icon="≈" label="近义词" value={knowledge.synonyms} />
            <KnRow icon="↔" label="反义词" value={knowledge.antonyms} />
            <KnRow icon="🔗" label="相关知识" value={knowledge.related} />
            <KnRow icon="💬" label="金句" value={knowledge.golden_quotes} />
            <KnRow icon="📋" label="规范表述" value={knowledge.formal_terms} />
            {knowledge.memory_tips && (
              <div><span className="text-muted-foreground">💡 记忆技巧：</span>{String(knowledge.memory_tips)}</div>
            )}
            {knowledge.essay_material && (
              <div><span className="text-muted-foreground">✍️ 申论素材：</span>{String(knowledge.essay_material)}</div>
            )}
          </div>
        </div>
      )}

      {/* Facts */}
      {facts && Object.keys(facts).length > 0 && (() => {
        // Filter out pinyin from facts if already displayed in dedicated section
        const factsEntries = Object.entries(facts).filter(([k]) => k !== "pinyin");
        if (factsEntries.length === 0) return null;
        return (
        <div className="bg-amber-50 dark:bg-amber-950/20 rounded-lg p-3">
          <div className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-1.5 flex items-center gap-1">
            📋 关键事实
          </div>
          <div className="grid gap-1 text-sm">
            {factsEntries.map(([k, v]) => {
              const { label, icon } = getFriendlyLabel(k);
              return (
                <div key={k} className="flex items-start gap-1">
                  <span className="text-muted-foreground shrink-0">{icon} {label}：</span>
                  <span>{v}</span>
                </div>
              );
            })}
          </div>
        </div>
        );
      })()}

      {/* Exam focus */}
      {examFocus && (
        <div className="flex flex-wrap gap-2">
          {examFocus.difficulty && (
            <Badge variant="outline" className="text-xs">
              {examFocus.difficulty === "easy" ? "🟢 简单" : examFocus.difficulty === "hard" ? "🔴 困难" : "🟡 中等"}
            </Badge>
          )}
          {examFocus.frequency && (
            <Badge variant="outline" className="text-xs">
              {examFocus.frequency === "high" ? "🔥 高频" : examFocus.frequency === "low" ? "⬇️ 低频" : "➡️ 中频"}
            </Badge>
          )}
        </div>
      )}

      {/* Alternate questions */}
      {altQuestions && altQuestions.length > 0 && (
        <div className="bg-indigo-50 dark:bg-indigo-950/20 rounded-lg p-3">
          <div className="text-xs font-semibold text-indigo-700 dark:text-indigo-400 mb-1.5 flex items-center gap-1">
            🔄 变体题目 ({altQuestions.length})
          </div>
          <div className="space-y-2">
            {altQuestions.map((aq: any, i: number) => (
              <div key={i} className="text-sm border-l-2 border-indigo-200 pl-2">
                <p className="font-medium">{aq.question}</p>
                <p className="text-xs text-muted-foreground">
                  答案：{aq.answer}
                  {aq.type && <span className="ml-2">类型：{aq.type}</span>}
                </p>
                {(() => {
                  const dists = aq.distractors || (aq.choices ? aq.choices.filter((c: string) => c !== aq.answer) : null);
                  return dists && dists.length > 0 ? (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {dists.map((d: string, j: number) => (
                        <Badge key={j} variant="outline" className="text-xs">
                          {d}
                        </Badge>
                      ))}
                    </div>
                  ) : null;
                })()}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Article Source Link */}
      {card.source && <ArticleSourceLink sourceUrl={card.source} />}

      {/* Source & metadata */}
      <div className="bg-gray-50 dark:bg-gray-900/30 rounded-lg p-3 space-y-1">
        <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 flex items-center gap-1">
          📊 卡片元信息
        </div>
        <div className="grid grid-cols-2 gap-1 text-xs text-muted-foreground">
          <span>状态: {["新卡片", "学习中", "复习中", "重新学习"][card.state] || "新卡片"}</span>
          <span>复习 {card.reps} 次</span>
          <span>遗忘 {card.lapses} 次</span>
          <span>稳定性 {(card.stability || 0).toFixed(1)}</span>
          <span>难度 {(card.difficulty || 0).toFixed(2)}</span>
          {card.tags && <span className="col-span-2">标签: {card.tags}</span>}
          {card.source && (
            <span className="col-span-2 truncate" title={card.source}>
              来源: {card.source}
            </span>
          )}
          {card.is_ai_generated && <span>🤖 AI生成</span>}
          {metaInfo?.knowledge_type && <span>知识类型: {knowledgeTypeLabel(metaInfo.knowledge_type)}</span>}
          {metaInfo?.subject && <span>主题: {metaInfo.subject}</span>}
        </div>
      </div>
    </div>
  );
}

/* ── Card Tag Manager (self-contained tag editing) ── */
export function CardTagManager({
  cardId,
  token,
  onClose,
  onTagsChange,
}: {
  cardId: number;
  token: string;
  onClose?: () => void;
  onTagsChange?: (tags: { id: number; name: string; color: string }[]) => void;
}) {
  const [allTags, setAllTags] = useState<any[]>([]);
  const [cardTags, setCardTags] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      tagsApi.list(token),
      tagsApi.getCardTags(cardId, token),
    ])
      .then(([tags, ct]) => {
        if (!cancelled) {
          setAllTags(tags);
          setCardTags(ct);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [cardId, token]);

  const toggleTag = async (tagId: number) => {
    const existing = cardTags.find((t: any) => t.id === tagId);
    try {
      if (existing) {
        await tagsApi.removeCardTag(cardId, tagId, token);
        const updated = cardTags.filter((t: any) => t.id !== tagId);
        setCardTags(updated);
        onTagsChange?.(updated);
      } else {
        await tagsApi.addCardTag(cardId, tagId, token);
        const tag = allTags.find((t: any) => t.id === tagId);
        if (tag) {
          const updated = [...cardTags, tag];
          setCardTags(updated);
          onTagsChange?.(updated);
        }
      }
    } catch { /* ignore */ }
  };

  const availableTags = allTags.filter(
    (t: any) => !cardTags.find((ct: any) => ct.id === t.id)
  );

  if (loading) {
    return (
      <div className="mt-3 pt-3 border-t text-xs text-muted-foreground">
        加载标签…
      </div>
    );
  }

  return (
    <div className="mt-3 pt-3 border-t space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">🏷️ 管理标签</span>
        {onClose && (
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-sm leading-none"
          >
            ✕
          </button>
        )}
      </div>
      <div className="flex items-center gap-1 flex-wrap">
        {cardTags.map((tag: any) => (
          <Badge
            key={tag.id}
            variant="secondary"
            className="text-xs cursor-pointer hover:bg-destructive/20"
            style={{ borderLeft: `3px solid ${tag.color || "#6b7280"}` }}
            onClick={() => toggleTag(tag.id)}
          >
            {tag.name} ×
          </Badge>
        ))}
        {availableTags.map((tag: any) => (
          <Badge
            key={tag.id}
            variant="outline"
            className="text-xs cursor-pointer hover:bg-primary/10"
            style={{ borderLeft: `3px solid ${tag.color || "#6b7280"}` }}
            onClick={() => toggleTag(tag.id)}
          >
            + {tag.name}
          </Badge>
        ))}
        {allTags.length === 0 && (
          <span className="text-xs text-muted-foreground">
            暂无标签，请先在标签管理中创建
          </span>
        )}
      </div>
    </div>
  );
}
