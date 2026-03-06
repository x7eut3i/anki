"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { saveSortPreference, loadSortPreference } from "@/lib/sort-preferences";
import { reading, ai, cards as cardsApi, categories as catApi, tags as tagsApi } from "@/lib/api";
import { MarkdownContent } from "@/components/markdown-content";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  BookMarked,
  Star,
  StarOff,
  Trash2,
  ChevronLeft,
  Plus,
  Loader2,
  Filter,
  ExternalLink,
  BookOpen,
  CheckCircle2,
  Sparkles,
  MessageCircle,
  Send,
  X,
  Bot,
  User,
  Layers,
  Eye,
  EyeOff,
  Globe,
  FileText,
  FileStack,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Search,
  Archive,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/timezone";
import { CardDetailPanel, CardTagManager, isHiddenTag } from "@/components/card-detail";

/* ── Clean excess blank lines while preserving paragraph spacing ── */
function cleanContent(text: string): string {
  // Normalize line endings
  let cleaned = text.replace(/\r\n/g, "\n");
  // Collapse 3+ consecutive newlines into double newline (paragraph break)
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  // Remove lines that are only whitespace
  cleaned = cleaned.replace(/\n[ \t]+\n/g, "\n\n");
  return cleaned.trim();
}

/* ── Types ── */
interface AnalysisItem {
  id: number;
  title: string;
  source_url: string;
  source_name: string;
  publish_date: string;
  quality_score: number;
  quality_reason: string;
  word_count: number;
  status: string;
  is_starred: boolean;
  created_at: string;
  updated_at: string;
  tags_list?: { id: number; name: string; color: string }[];
}

interface Highlight {
  text: string;
  type: string;
  color: string;
  annotation: string;
}

interface AnalysisJSON {
  summary?: string;
  quality_score?: number;
  quality_reason?: string;
  overall_analysis?: {
    theme?: string;
    structure?: string;
    writing_style?: string;
    core_arguments?: string[];
    logical_chain?: string;
    shenglun_guidance?: string;
  };
  highlights?: Highlight[];
  exam_points?: {
    essay_angles?: (string | { angle: string; reference_answer: string })[];
    formal_terms?: string[];
    golden_quotes?: string[];
    background_knowledge?: string[];
    possible_questions?: (string | { question: string; question_type?: string; reference_answer: string })[];
  };
  vocabulary?: { term: string; explanation: string }[];
  reading_notes?: string;
}

interface AnalysisDetail extends AnalysisItem {
  content: string;
  analysis_html: string;
  analysis_json: AnalysisJSON;
  finished_at: string | null;
}

/* ── Status helpers ── */
const STATUS_LABELS: Record<string, { text: string; color: string; icon: React.ReactNode }> = {
  new: { text: "新", color: "bg-blue-100 text-blue-700", icon: <Sparkles className="h-3 w-3" /> },
  reading: { text: "在读", color: "bg-amber-100 text-amber-700", icon: <BookOpen className="h-3 w-3" /> },
  finished: { text: "已读", color: "bg-green-100 text-green-700", icon: <CheckCircle2 className="h-3 w-3" /> },
  archived: { text: "归档", color: "bg-gray-100 text-gray-500", icon: <Archive className="h-3 w-3" /> },
};

const COLOR_MAP: Record<string, string> = {
  red: "#ef4444", orange: "#f97316", blue: "#3b82f6",
  green: "#22c55e", purple: "#a855f7",
};

const TYPE_LABELS: Record<string, string> = {
  key_point: "核心观点", policy: "政策要点", data: "数据支撑",
  quote: "金句", terminology: "术语", exam_focus: "考点",
  vocabulary: "词汇", formal_term: "规范表述",
};

function QualityBadge({ score }: { score: number }) {
  let color = "bg-gray-100 text-gray-600";
  if (score >= 9) color = "bg-red-100 text-red-700";
  else if (score >= 7) color = "bg-orange-100 text-orange-700";
  else if (score >= 5) color = "bg-blue-100 text-blue-700";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      ⭐ {score}/10
    </span>
  );
}

/* ── Annotated Text Component ── */
function AnnotatedText({
  content,
  highlights,
}: {
  content: string;
  highlights: Highlight[];
}) {
  const [activePopup, setActivePopup] = useState<number | null>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  // Reposition popup to stay within viewport
  useEffect(() => {
    if (activePopup === null || !popupRef.current) return;
    const el = popupRef.current;
    const rect = el.getBoundingClientRect();
    // Fix right overflow
    if (rect.right > window.innerWidth - 8) {
      el.style.left = "auto";
      el.style.right = "0";
    }
    // Fix left overflow
    if (rect.left < 8) {
      el.style.left = "0";
      el.style.right = "auto";
    }
    // Fix bottom overflow — show above instead
    if (rect.bottom > window.innerHeight - 8) {
      el.style.top = "auto";
      el.style.bottom = "100%";
      el.style.marginBottom = "4px";
      el.style.marginTop = "0";
    }
  }, [activePopup]);

  // Close popup on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        setActivePopup(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Find all highlight positions in the text
  const positions: { start: number; end: number; highlight: Highlight; index: number }[] = [];
  highlights.forEach((h, idx) => {
    if (!h.text) return;
    const pos = content.indexOf(h.text);
    if (pos >= 0) {
      positions.push({ start: pos, end: pos + h.text.length, highlight: h, index: idx });
    }
  });

  // Sort by position and remove overlaps
  positions.sort((a, b) => a.start - b.start);
  const filtered: typeof positions = [];
  for (const p of positions) {
    if (filtered.length === 0 || p.start >= filtered[filtered.length - 1].end) {
      filtered.push(p);
    }
  }

  // Build segments
  const segments: { text: string; highlight?: Highlight; index?: number }[] = [];
  let cursor = 0;
  for (const p of filtered) {
    if (p.start > cursor) {
      segments.push({ text: content.slice(cursor, p.start) });
    }
    segments.push({ text: p.highlight.text, highlight: p.highlight, index: p.index });
    cursor = p.end;
  }
  if (cursor < content.length) {
    segments.push({ text: content.slice(cursor) });
  }

  return (
    <div className="relative leading-[2] text-[15px]">
      {segments.map((seg, i) => {
        if (!seg.highlight) {
          return (
            <span key={i} className="whitespace-pre-wrap">
              {seg.text}
            </span>
          );
        }

        const color = COLOR_MAP[seg.highlight.color] || "#3b82f6";
        const isActive = activePopup === seg.index;

        return (
          <span key={i} className="relative inline">
            <span
              className="cursor-pointer transition-all duration-200 border-b-2 hover:bg-opacity-20"
              style={{
                borderColor: color,
                backgroundColor: isActive ? `${color}20` : "transparent",
              }}
              onClick={() => setActivePopup(isActive ? null : (seg.index ?? null))}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.backgroundColor = `${color}15`;
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  (e.currentTarget as HTMLElement).style.backgroundColor = "transparent";
                }
              }}
            >
              {seg.text}
            </span>

            {/* Popup annotation */}
            {isActive && (
              <span
                ref={popupRef}
                className="absolute z-50 left-0 top-full mt-1 w-[min(20rem,calc(100vw-2rem))] bg-card border rounded-xl shadow-xl p-4 text-sm animate-in fade-in slide-in-from-top-2 duration-200"
                style={{ borderTopColor: color, borderTopWidth: 3 }}
                onClick={(e) => e.stopPropagation()}
              >
                <span className="flex items-center gap-2 mb-2">
                  <span
                    className="text-[11px] text-white px-2 py-0.5 rounded-full font-medium"
                    style={{ backgroundColor: color }}
                  >
                    {TYPE_LABELS[seg.highlight.type] || seg.highlight.type}
                  </span>
                  <button
                    className="ml-auto text-muted-foreground hover:text-foreground"
                    onClick={() => setActivePopup(null)}
                    title="关闭"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </span>
                <span className="block text-muted-foreground leading-relaxed">
                  {seg.highlight.annotation}
                </span>
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

/* ── AI Chat Panel ── */
function ArticleChat({
  title,
  content,
  onClose,
}: {
  title: string;
  content: string;
  onClose: () => void;
}) {
  const { token } = useAuthStore();
  const [messages, setMessages] = useState<
    { role: "user" | "assistant"; content: string }[]
  >([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!token || !input.trim() || loading) return;
    const msg = input.trim();
    setInput("");

    const contextPrefix = messages.length === 0
      ? `我正在精读一篇文章《${title}》，以下是文章内容摘要（前2000字）：\n\n${content.slice(0, 2000)}\n\n请基于这篇文章回答我的问题：\n\n`
      : "";

    const updatedMessages = [...messages, { role: "user" as const, content: msg }];
    setMessages(updatedMessages);
    setLoading(true);

    try {
      const history = updatedMessages.map((m, i) => ({
        role: m.role,
        content: i === 0 && messages.length === 0 ? contextPrefix + m.content : m.content,
      }));
      const resp = await ai.chat(
        { message: contextPrefix + msg, history },
        token
      );
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: resp.response || resp.reply || resp.message || "..." },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "抱歉，AI 回复失败。请检查AI配置。" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full border-l bg-card">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <MessageCircle className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">AI 问答</span>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground" title="关闭问答">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-muted-foreground text-sm py-8">
            <Bot className="h-8 w-8 mx-auto mb-2 opacity-40" />
            <p>关于这篇文章，你有什么问题？</p>
            <div className="flex flex-wrap gap-1.5 mt-3 justify-center">
              {["核心论点是什么？", "有哪些申论素材？", "总结考试要点"].map((q) => (
                <button
                  key={q}
                  className="text-xs bg-muted px-2.5 py-1 rounded-full hover:bg-primary/10 transition-colors"
                  onClick={() => setInput(q)}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === "user" ? "justify-end" : ""}`}>
            {m.role === "assistant" && (
              <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                <Bot className="h-3 w-3 text-primary" />
              </div>
            )}
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
              }`}
            >
              {m.role === "assistant" ? (
                <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{m.content}</p>
              )}
            </div>
            {m.role === "user" && (
              <div className="h-6 w-6 rounded-full bg-secondary flex items-center justify-center shrink-0 mt-0.5">
                <User className="h-3 w-3" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-2">
            <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="h-3 w-3 text-primary" />
            </div>
            <div className="bg-muted rounded-lg px-3 py-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            </div>
          </div>
        )}
      </div>

      <div className="border-t p-3 flex gap-2">
        <Input
          placeholder="问一下这篇文章..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          className="h-9 text-sm"
        />
        <Button size="sm" onClick={handleSend} disabled={loading || !input.trim()} className="h-9 px-3" title="发送">
          <Send className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

/* ── Collapsible Reference Answer ── */
function RefAnswer({ answer }: { answer: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="mt-2">
      <button
        className="text-xs text-primary hover:text-primary/80 flex items-center gap-1 font-medium"
        onClick={() => setShow(!show)}
      >
        {show ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
        {show ? "隐藏参考答案" : "查看参考答案"}
      </button>
      {show && (
        <div className="mt-2 bg-blue-50 dark:bg-blue-950/30 rounded-lg p-3 text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap border-l-2 border-primary/30">
          {answer}
        </div>
      )}
    </div>
  );
}

/* ── Structured Analysis View ── */
function StructuredAnalysis({ data }: { data: AnalysisJSON }) {
  if (!data) return <p className="text-muted-foreground">暂无分析数据</p>;

  return (
    <div className="space-y-6">
      {/* Summary */}
      {data.summary && (
        <section className="bg-blue-50 dark:bg-blue-950/30 rounded-xl p-5">
          <h3 className="text-base font-bold mb-2">📋 文章概述</h3>
          <p className="text-sm leading-relaxed text-muted-foreground">{data.summary}</p>
        </section>
      )}

      {/* Overall Analysis */}
      {data.overall_analysis && (
        <section className="bg-card rounded-xl border p-5 space-y-3">
          <h3 className="text-base font-bold">🔍 整体分析</h3>
          {data.overall_analysis.theme && (
            <div className="flex gap-2 text-sm">
              <span className="font-medium shrink-0 text-primary">主题</span>
              <span className="text-muted-foreground">{data.overall_analysis.theme}</span>
            </div>
          )}
          {data.overall_analysis.structure && (
            <div className="flex gap-2 text-sm">
              <span className="font-medium shrink-0 text-primary">结构</span>
              <span className="text-muted-foreground">{data.overall_analysis.structure}</span>
            </div>
          )}
          {data.overall_analysis.writing_style && (
            <div className="flex gap-2 text-sm">
              <span className="font-medium shrink-0 text-primary">写作特点</span>
              <span className="text-muted-foreground">{data.overall_analysis.writing_style}</span>
            </div>
          )}
          {data.overall_analysis.core_arguments && data.overall_analysis.core_arguments.length > 0 && (
            <div>
              <span className="font-medium text-sm text-primary">核心论点</span>
              <ul className="mt-1 space-y-1">
                {data.overall_analysis.core_arguments.map((a, i) => (
                  <li key={i} className="text-sm text-muted-foreground flex gap-2">
                    <span className="text-primary shrink-0">•</span> {a}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.overall_analysis.logical_chain && (
            <div className="flex gap-2 text-sm">
              <span className="font-medium shrink-0 text-primary">论证逻辑</span>
              <span className="text-muted-foreground">{data.overall_analysis.logical_chain}</span>
            </div>
          )}
          {data.overall_analysis.shenglun_guidance && (
            <div className="mt-3 pt-3 border-t">
              <span className="font-medium text-sm text-primary">✍️ 申论写作指导</span>
              <div className="mt-1">
                <MarkdownContent content={data.overall_analysis.shenglun_guidance} />
              </div>
            </div>
          )}
        </section>
      )}

      {/* Highlights */}
      {data.highlights && data.highlights.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-base font-bold">✨ 重点标注 ({data.highlights.length})</h3>
          <div className="space-y-2">
            {data.highlights.map((h, i) => {
              const color = COLOR_MAP[h.color] || "#3b82f6";
              return (
                <div
                  key={i}
                  className="rounded-lg p-4 transition-all hover:shadow-sm"
                  style={{ borderLeft: `4px solid ${color}`, background: `${color}08` }}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className="text-[11px] text-white px-2 py-0.5 rounded-full shrink-0 mt-0.5"
                      style={{ backgroundColor: color }}
                    >
                      {TYPE_LABELS[h.type] || h.type}
                    </span>
                    <span className="text-sm font-medium" style={{ color }}>
                      &ldquo;{h.text}&rdquo;
                    </span>
                  </div>
                  {h.annotation && (
                    <p className="text-xs text-muted-foreground mt-2 ml-1 leading-relaxed">
                      {h.annotation}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Exam Points */}
      {data.exam_points && (
        <section className="space-y-3">
          <h3 className="text-base font-bold">🎯 考试要点</h3>
          <div className="grid gap-3">
            {/* Essay Angles */}
            {data.exam_points.essay_angles && data.exam_points.essay_angles.length > 0 && (
              <div className="bg-card rounded-lg border p-4">
                <h4 className="text-sm font-semibold mb-2">📝 申论角度</h4>
                <div className="space-y-3">
                  {data.exam_points.essay_angles.map((item, i) => {
                    const isObj = typeof item === "object" && item !== null;
                    const text = isObj ? (item as any).angle : item;
                    const ref = isObj ? (item as any).reference_answer : null;
                    return (
                      <div key={i}>
                        <div className="text-sm text-muted-foreground flex gap-2">
                          <span className="text-primary shrink-0">•</span> {text}
                        </div>
                        {ref && <RefAnswer answer={ref} />}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Possible Questions */}
            {data.exam_points.possible_questions && data.exam_points.possible_questions.length > 0 && (
              <div className="bg-card rounded-lg border p-4">
                <h4 className="text-sm font-semibold mb-2">❓ 可能考法</h4>
                <div className="space-y-3">
                  {data.exam_points.possible_questions.map((item, i) => {
                    const isObj = typeof item === "object" && item !== null;
                    const text = isObj ? (item as any).question : item;
                    const qtype = isObj ? (item as any).question_type : null;
                    const ref = isObj ? (item as any).reference_answer : null;
                    return (
                      <div key={i}>
                        <div className="text-sm text-muted-foreground flex gap-2">
                          <span className="text-primary shrink-0">•</span>
                          <span>{text}</span>
                          {qtype && (
                            <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded shrink-0">{qtype}</span>
                          )}
                        </div>
                        {ref && <RefAnswer answer={ref} />}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Simple list sections */}
            {(["formal_terms", "golden_quotes", "background_knowledge"] as const).map((key) => {
              const labels: Record<string, string> = {
                formal_terms: "📋 规范表述",
                golden_quotes: "💬 金句",
                background_knowledge: "📚 背景知识",
              };
              const items = data.exam_points?.[key];
              if (!items || items.length === 0) return null;
              return (
                <div key={key} className="bg-card rounded-lg border p-4">
                  <h4 className="text-sm font-semibold mb-2">{labels[key]}</h4>
                  <ul className="space-y-1">
                    {items.map((item, i) => (
                      <li key={i} className="text-sm text-muted-foreground flex gap-2">
                        <span className="text-primary shrink-0">•</span> {item}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Vocabulary */}
      {data.vocabulary && data.vocabulary.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-base font-bold">📖 重要术语</h3>
          <div className="grid gap-2">
            {data.vocabulary.map((v, i) => (
              <div key={i} className="bg-card rounded-lg border p-3 flex gap-3 items-baseline">
                <span className="font-semibold text-sm text-primary shrink-0">{v.term}</span>
                <span className="text-sm text-muted-foreground">{v.explanation}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Reading Notes */}
      {data.reading_notes && (
        <section className="bg-amber-50 dark:bg-amber-950/30 rounded-xl p-5">
          <h3 className="text-base font-bold mb-2">📝 阅读笔记</h3>
          <MarkdownContent content={data.reading_notes} />
        </section>
      )}
    </div>
  );
}

/* ── Main Page ── */
export default function ReadingPage() {
  const { token } = useAuthStore();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [cameFromExternal] = useState(() => !!searchParams.get("article_id"));
  const [items, setItems] = useState<AnalysisItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [starredOnly, setStarredOnly] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceNames, setSourceNames] = useState<string[]>([]);
  const [failedOnly, setFailedOnly] = useState(false);
  const [tagFilter, setTagFilter] = useState<number | null>(null);
  const [filterTags, setFilterTags] = useState<any[]>([]);

  // Batch operations
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [batchReanalyzing, setBatchReanalyzing] = useState(false);

  // Sorting
  const [sortBy, setSortBy] = useState<string>(() => loadSortPreference("reading", { sortKey: "created_at", sortDir: "desc" }).sortKey);
  const [sortDir, setSortDir] = useState<string>(() => loadSortPreference("reading", { sortKey: "created_at", sortDir: "desc" }).sortDir);

  // Persist sort preferences
  useEffect(() => {
    saveSortPreference("reading", { sortKey: sortBy, sortDir: sortDir as "asc" | "desc" });
  }, [sortBy, sortDir]);

  // Detail view
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(() => cameFromExternal);

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: "",
    content: "",
    source_url: "",
    source_name: "",
    publish_date: "",
  });
  const [creating, setCreating] = useState(false);
  const [creatingMode, setCreatingMode] = useState<"analysis" | "cards">("analysis");
  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [urlInput, setUrlInput] = useState("");

  // Active tab in detail view
  const [activeTab, setActiveTab] = useState<"annotated" | "analysis">("annotated");

  // AI Chat
  const [showChat, setShowChat] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);

  // Text selection → create card
  const [selectedText, setSelectedText] = useState("");
  const [cardCreating, setCardCreating] = useState(false);
  const [cardResult, setCardResult] = useState<any>(null);
  const [categoryList, setCategoryList] = useState<any[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);

  // Related cards from this article
  const [relatedCards, setRelatedCards] = useState<any[]>([]);
  const [showRelatedCards, setShowRelatedCards] = useState(true);
  const [expandedCardId, setExpandedCardId] = useState<number | null>(null);

  // Toast notification (replaces alert popups)
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" | "info" } | null>(null);
  const showToast = useCallback((message: string, type: "success" | "error" | "info" = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  // Article tags
  const [articleTags, setArticleTags] = useState<any[]>([]);
  const [allTags, setAllTags] = useState<any[]>([]);
  const [showTagDropdown, setShowTagDropdown] = useState(false);

  /* ── Fetch list ── */
  const fetchList = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const params: Record<string, any> = { page, page_size: 20 };
      if (statusFilter) params.status = statusFilter;
      if (starredOnly) params.is_starred = true;
      if (sourceFilter) params.source_name = sourceFilter;
      if (searchQuery.trim()) params.search = searchQuery.trim();
      if (sortBy) params.sort_by = sortBy;
      if (sortDir) params.sort_dir = sortDir;
      if (failedOnly) params.min_quality = 0;
      if (tagFilter) params.tag_id = tagFilter;
      const data = await reading.list(params, token);
      setItems(failedOnly ? data.items.filter((i: any) => i.quality_score === 0) : data.items);
      setTotal(data.total);
      if (data.source_names) setSourceNames(data.source_names);
      setSelectedIds(new Set());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, page, statusFilter, starredOnly, sourceFilter, searchQuery, sortBy, sortDir, failedOnly, tagFilter]);

  useEffect(() => { fetchList(); }, [fetchList]);

  // Load tags for filter dropdown
  useEffect(() => {
    if (!token) return;
    tagsApi.list(token).then(setFilterTags).catch(() => {});
  }, [token]);

  /* ── Open detail ── */
  const openDetail = async (id: number) => {
    if (!token) return;
    setLoadingDetail(true);
    try {
      const data = await reading.get(id, token);
      setDetail(data);
      if (data.status === "new") {
        await reading.updateStatus(id, "reading", token);
        setItems((prev) =>
          prev.map((i) => (i.id === id ? { ...i, status: "reading" } : i))
        );
      }
      // Load article tags
      try {
        const [tags, artTags] = await Promise.all([
          tagsApi.list(token),
          tagsApi.getArticleTags(id, token),
        ]);
        setAllTags(tags);
        setArticleTags(artTags);
      } catch { /* ignore */ }
    } catch {
      /* ignore */
    } finally {
      setLoadingDetail(false);
    }
  };

  /* ── Auto-open article from URL param (e.g. /reading?article_id=123) ── */
  useEffect(() => {
    const articleId = searchParams.get("article_id");
    if (articleId && token && !detail) {
      openDetail(parseInt(articleId));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, searchParams]);

  /* ── Toggle star ── */
  const toggleStar = async (id: number, currentStarred: boolean) => {
    if (!token) return;
    await reading.updateStar(id, !currentStarred, token);
    setItems((prev) =>
      prev.map((i) => (i.id === id ? { ...i, is_starred: !currentStarred } : i))
    );
    if (detail?.id === id) {
      setDetail((d) => d ? { ...d, is_starred: !currentStarred } : d);
    }
  };

  /* ── Update status ── */
  const updateStatus = async (id: number, newStatus: string) => {
    if (!token) return;
    await reading.updateStatus(id, newStatus, token);
    setItems((prev) =>
      prev.map((i) => (i.id === id ? { ...i, status: newStatus } : i))
    );
    if (detail?.id === id) {
      setDetail((d) => d ? { ...d, status: newStatus } : d);
    }
  };

  /* ── Delete ── */
  const handleDelete = async (id: number) => {
    if (!token || !confirm("确定要删除这篇精读分析吗？")) return;
    await reading.delete(id, token);
    setItems((prev) => prev.filter((i) => i.id !== id));
    setTotal((t) => t - 1);
    if (detail?.id === id) setDetail(null);
  };

  /* ── Create ── */
  const handleCreate = async (withCards: boolean) => {
    if (!token || !createForm.title.trim() || !createForm.content.trim()) return;
    setCreating(true);
    setCreatingMode(withCards ? "cards" : "analysis");
    try {
      const result = await reading.create({ ...createForm, create_cards: withCards }, token);
      setShowCreate(false);
      setCreateForm({ title: "", content: "", source_url: "", source_name: "", publish_date: "" });
      setUrlInput("");
      fetchList();
      // Show async job notification
      if (result?.job_id) {
        showToast("文章已提交，AI正在后台分析中", "success");
      }
    } catch (e: any) {
      showToast(e.message || "创建失败", "error");
    } finally {
      setCreating(false);
    }
  };

  /* ── Fetch URL ── */
  const handleFetchUrl = async () => {
    if (!token || !urlInput.trim()) return;
    setFetchingUrl(true);
    try {
      const data = await reading.fetchUrl(urlInput.trim(), token);
      setCreateForm((f) => ({
        ...f,
        title: data.title || f.title,
        content: data.content || f.content,
        source_url: data.url || urlInput.trim(),
        source_name: data.source_name || f.source_name,
        publish_date: data.publish_date || f.publish_date,
      }));
    } catch (e: any) {
      showToast(e.message || "URL获取失败，请手动填写", "error");
    } finally {
      setFetchingUrl(false);
    }
  };

  const totalPages = Math.ceil(total / 20);

  /* ── Load categories for card creation ── */
  useEffect(() => {
    if (!token) return;
    catApi.list(token).then((data: any) => {
      setCategoryList(data.categories || data || []);
    }).catch(() => {});
  }, [token]);

  /* ── Handle text selection for card creation ── */
  const handleTextSelect = useCallback(() => {
    const sel = window.getSelection();
    const text = sel?.toString().trim() || "";
    if (text.length >= 4) {
      setSelectedText(text);
      setCardResult(null);
    }
  }, []);

  /* ── Create card from selection ── */
  const handleCreateCard = async () => {
    if (!token || !selectedText || !detail) return;
    setCardCreating(true);
    setCardResult(null);
    try {
      const result = await reading.createCard({
        selected_text: selectedText,
        article_title: detail.title,
        article_content: detail.content,
        source_url: detail.source_url,
        category_id: selectedCategoryId,
        preview: true,
      }, token);
      setCardResult(result);
    } catch (e: any) {
      setCardResult({ error: e.message || "创建失败" });
    } finally {
      setCardCreating(false);
    }
  };

  /* ── Save previewed card ── */
  const handleSavePreviewCard = async () => {
    if (!token || !cardResult || cardResult.error || !cardResult.preview) return;
    setCardCreating(true);
    try {
      const result = await reading.savePreviewCard({
        front: cardResult.front,
        back: cardResult.back,
        explanation: cardResult.explanation || "",
        distractors: cardResult.distractors || [],
        tags: cardResult.tags || "",
        category_id: cardResult.category_id || selectedCategoryId,
        meta_info: cardResult.meta_info || {},
        source_url: detail?.source_url || "",
      }, token);
      setCardResult({ ...result, saved: true });
      // Refresh related cards
      if (detail) loadRelatedCards(detail.source_url);
    } catch (e: any) {
      setCardResult({ error: e.message || "保存失败" });
    } finally {
      setCardCreating(false);
    }
  };

  /* ── Load related cards ── */
  const loadRelatedCards = async (sourceUrl: string, title?: string) => {
    if (!token) return;
    try {
      let cards: any[] = [];
      // Try by source URL first
      if (sourceUrl) {
        const data = await cardsApi.list({ source: sourceUrl, page_size: 50 }, token);
        cards = data.cards || data.items || [];
      }
      // Fallback: search by article title
      if (cards.length === 0 && title) {
        const data = await cardsApi.list({ search: title.slice(0, 20), page_size: 50 }, token);
        cards = data.cards || data.items || [];
      }
      setRelatedCards(cards);
    } catch {
      setRelatedCards([]);
    }
  };

  /* ── Load related cards when detail opens ── */
  useEffect(() => {
    if (detail && token) {
      loadRelatedCards(detail.source_url || "", detail.title);
    } else {
      setRelatedCards([]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id, token]);

  /* ── Detail View ── */
  if (detail) {
    // Merge vocabulary and formal_terms into highlights for richer annotation
    const baseHighlights = detail.analysis_json?.highlights || [];
    const extraHighlights: Highlight[] = [];
    // Add vocabulary terms not already in highlights
    if (detail.analysis_json?.vocabulary) {
      const existingTexts = new Set(baseHighlights.map(h => h.text));
      for (const v of detail.analysis_json.vocabulary) {
        if (v.term && !existingTexts.has(v.term) && detail.content.includes(v.term)) {
          extraHighlights.push({ text: v.term, type: "vocabulary", color: "purple", annotation: v.explanation });
          existingTexts.add(v.term);
        }
      }
    }
    // Add formal_terms not already in highlights
    if (detail.analysis_json?.exam_points?.formal_terms) {
      const existingTexts2 = new Set([...baseHighlights, ...extraHighlights].map(h => h.text));
      for (const ft of detail.analysis_json.exam_points.formal_terms) {
        if (ft && !existingTexts2.has(ft) && detail.content.includes(ft)) {
          extraHighlights.push({ text: ft, type: "formal_term", color: "orange", annotation: `公文规范表述：${ft}` });
          existingTexts2.add(ft);
        }
      }
    }
    const highlights = [...baseHighlights, ...extraHighlights];

    return (
      <div className="flex flex-col md:flex-row h-[calc(100vh-64px)]">
        {/* Main content */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-3 sm:px-6 py-4 sm:py-6 space-y-4">
            {/* Back */}
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="sm" onClick={() => {
                if (cameFromExternal) {
                  router.back();
                } else {
                  setDetail(null);
                  setShowChat(false);
                  fetchList();
                }
              }}>
                <ChevronLeft className="h-4 w-4 mr-1" /> 返回列表
              </Button>
            </div>

            {/* Title bar */}
            <div className="bg-card rounded-xl border p-6">
              <div>
                <h1 className="text-xl font-bold mb-2">{detail.title}</h1>
                <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  {detail.source_name && (
                    <span className="bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded text-xs">{detail.source_name}</span>
                  )}
                  {detail.publish_date && <span>{detail.publish_date}</span>}
                  <QualityBadge score={detail.quality_score} />
                  {detail.quality_reason && (
                    <span className="text-xs text-muted-foreground">— {detail.quality_reason}</span>
                  )}
                  <span className="text-xs">{detail.word_count} 字</span>
                </div>
                {/* Article tags */}
                <div className="flex flex-wrap items-center gap-1.5 mt-2">
                    {articleTags.map((tag: any) => (
                      <Badge
                        key={tag.id}
                        className="cursor-pointer text-xs"
                        style={{ backgroundColor: tag.color || '#6366f1', color: '#fff' }}
                        onClick={async () => {
                          if (!token) return;
                          await tagsApi.removeArticleTag(detail.id, tag.id, token);
                          setArticleTags((prev) => prev.filter((t: any) => t.id !== tag.id));
                        }}
                      >
                        {tag.name} ×
                      </Badge>
                    ))}
                    <div className="relative">
                      <button
                        className="text-xs text-muted-foreground hover:text-primary border border-dashed rounded-md px-2 py-0.5 hover:bg-muted/50"
                        onClick={() => setShowTagDropdown(!showTagDropdown)}
                      >
                        + 标签
                      </button>
                      {showTagDropdown && (
                        <div className="absolute z-50 top-full left-0 mt-1 bg-card border rounded-lg shadow-lg p-2 min-w-[140px]">
                          {allTags.filter((t: any) => !articleTags.find((at: any) => at.id === t.id)).map((tag: any) => (
                            <button
                              key={tag.id}
                              className="w-full text-left text-xs px-2 py-1.5 rounded hover:bg-muted flex items-center gap-2"
                              onClick={async () => {
                                if (!token) return;
                                await tagsApi.addArticleTag(detail.id, tag.id, token);
                                setArticleTags((prev) => [...prev, tag]);
                                setShowTagDropdown(false);
                              }}
                            >
                              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: tag.color || '#6366f1' }} />
                              {tag.name}
                            </button>
                          ))}
                          {allTags.filter((t: any) => !articleTags.find((at: any) => at.id === t.id)).length === 0 && (
                            <span className="text-xs text-muted-foreground px-2 py-1">无更多标签</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                
                {/* Action buttons - moved below title/meta section */}
                <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t">
                  {detail.status === "archived" ? (
                    <Button size="sm" variant="outline" onClick={() => updateStatus(detail.id, "new")}>
                      <Archive className="h-3.5 w-3.5 mr-1" /> 取消归档
                    </Button>
                  ) : detail.status !== "finished" ? (
                    <Button size="sm" variant="outline" onClick={() => updateStatus(detail.id, "finished")}>
                      <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> 标记已读
                    </Button>
                  ) : (
                    <>
                      <Button size="sm" variant="outline" onClick={() => updateStatus(detail.id, "reading")}>
                        <BookOpen className="h-3.5 w-3.5 mr-1" /> 重新阅读
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => updateStatus(detail.id, "archived")}>
                        <Archive className="h-3.5 w-3.5 mr-1" /> 归档
                      </Button>
                    </>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => toggleStar(detail.id, detail.is_starred)} title={detail.is_starred ? "取消收藏" : "收藏"}>
                    {detail.is_starred ? (
                      <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                    ) : (
                      <StarOff className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant={showChat ? "default" : "outline"}
                    onClick={() => setShowChat(!showChat)}
                  >
                    <MessageCircle className="h-3.5 w-3.5 mr-1" /> AI问答
                  </Button>
                  {(!detail.analysis_json || Object.keys(detail.analysis_json).length === 0) ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-orange-600 border-orange-300"
                      disabled={reanalyzing}
                      onClick={async () => {
                        if (!token || reanalyzing) return;
                        setReanalyzing(true);
                        try {
                          const res = await reading.reanalyze(detail.id, token);
                          showToast("重新分析任务已提交", "success");
                          // Refresh after a short delay
                          setTimeout(async () => {
                            try {
                              const updated = await reading.get(detail.id, token);
                              setDetail(updated);
                            } catch {}
                          }, 2000);
                        } catch (e: any) {
                          showToast(e.message || "重新分析失败", "error");
                        } finally {
                          setReanalyzing(false);
                        }
                      }}
                    >
                      {reanalyzing ? (
                        <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> 分析中...</>
                      ) : (
                        <><Sparkles className="h-3.5 w-3.5 mr-1" /> 分析</>
                      )}
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={reanalyzing}
                      onClick={async () => {
                        if (!token || reanalyzing) return;
                        if (!confirm("确定重新分析？这将覆盖现有分析结果。")) return;
                        setReanalyzing(true);
                        try {
                          const res = await reading.reanalyze(detail.id, token);
                          showToast("重新分析任务已提交", "success");
                          setTimeout(async () => {
                            try {
                              const updated = await reading.get(detail.id, token);
                              setDetail(updated);
                            } catch {}
                          }, 2000);
                        } catch (e: any) {
                          showToast(e.message || "重新分析失败", "error");
                        } finally {
                          setReanalyzing(false);
                        }
                      }}
                    >
                      {reanalyzing ? (
                        <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> 分析中...</>
                      ) : (
                        <><Sparkles className="h-3.5 w-3.5 mr-1" /> 重新分析</>
                      )}
                    </Button>
                  )}
                  {detail.source_url && (
                    <Button size="sm" variant="ghost" asChild title="查看原文">
                      <a href={detail.source_url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </Button>
                  )}
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-muted rounded-lg p-1">
              <button
                className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === "annotated" ? "bg-card shadow text-foreground" : "text-muted-foreground"
                }`}
                onClick={() => setActiveTab("annotated")}
              >
                🖍️ 标注阅读
              </button>
              <button
                className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === "analysis" ? "bg-card shadow text-foreground" : "text-muted-foreground"
                }`}
                onClick={() => setActiveTab("analysis")}
              >
                ✨ 精读分析
              </button>
            </div>

            {/* Highlight legend */}
            {activeTab === "annotated" && highlights.length > 0 && (
              <div className="flex flex-wrap items-center gap-3 px-1 text-xs text-muted-foreground">
                <span className="font-medium">标注图例：</span>
                {Object.entries(TYPE_LABELS).map(([key, label]) => {
                  const count = highlights.filter(h => h.type === key).length;
                  if (count === 0) return null;
                  const hColor = highlights.find(h => h.type === key)?.color || "blue";
                  return (
                    <span key={key} className="flex items-center gap-1">
                      <span className="w-3 h-0.5 rounded" style={{ backgroundColor: COLOR_MAP[hColor] || "#3b82f6" }} />
                      {label} ({count})
                    </span>
                  );
                })}
                <span className="text-muted-foreground/60">· 点击下划线文字查看批注</span>
              </div>
            )}

            {/* Content */}
            <div className="bg-card rounded-xl border p-6" onMouseUp={handleTextSelect}>
              {activeTab === "annotated" ? (
                highlights.length > 0 ? (
                  <AnnotatedText content={cleanContent(detail.content)} highlights={highlights} />
                ) : (
                  <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-[1.9] text-[15px] reading-content">
                    {cleanContent(detail.content)}
                  </div>
                )
              ) : (
                detail.analysis_json && Object.keys(detail.analysis_json).length > 0 ? (
                  <StructuredAnalysis data={detail.analysis_json} />
                ) : (
                  <div
                    className="prose prose-sm max-w-none reading-analysis"
                    dangerouslySetInnerHTML={{ __html: detail.analysis_html }}
                  />
                )
              )}
            </div>

            {/* Floating selection toolbar + card creation */}
            {selectedText && (
              <div className="sticky bottom-4 z-40">
                <div className="max-w-xl mx-auto bg-card border shadow-lg rounded-xl px-4 py-3 space-y-3 animate-in slide-in-from-bottom-2">
                  <div className="flex items-center gap-3">
                    <div className="text-sm text-muted-foreground flex-1 truncate">
                      &ldquo;{selectedText}&rdquo;
                    </div>
                    <Button
                      size="sm"
                      onClick={handleCreateCard}
                      disabled={cardCreating}
                      className="shrink-0"
                    >
                      {cardCreating ? (
                        <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> 生成中...</>
                      ) : (
                        <><Sparkles className="h-3.5 w-3.5 mr-1" /> 生成卡片</>
                      )}
                    </Button>
                    <button
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => { setSelectedText(""); setCardResult(null); }}
                      title="关闭"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  {cardResult && (
                    <div className={`rounded-lg p-3 text-sm ${cardResult.error ? "bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400" : "bg-muted/50"}`}>
                      {cardResult.error ? (
                        <p>❌ {cardResult.error}</p>
                      ) : cardResult.saved ? (
                        <div className="text-green-700 dark:text-green-400 space-y-1">
                          <p>✅ 卡片已保存！分类：{cardResult.category || "未分类"}</p>
                          <p className="text-xs"><strong>正面：</strong>{cardResult.front}</p>
                          <p className="text-xs"><strong>背面：</strong>{cardResult.back}</p>
                        </div>
                      ) : cardResult.preview ? (
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-muted-foreground">📋 卡片预览 — 确认后保存</div>
                          <div className="space-y-1.5">
                            <div><span className="text-xs font-medium">正面：</span>
                              <input className="w-full text-xs p-1 border rounded bg-background" value={cardResult.front}
                                onChange={(e) => setCardResult({ ...cardResult, front: e.target.value })} />
                            </div>
                            <div><span className="text-xs font-medium">背面：</span>
                              <input className="w-full text-xs p-1 border rounded bg-background" value={cardResult.back}
                                onChange={(e) => setCardResult({ ...cardResult, back: e.target.value })} />
                            </div>
                            <div><span className="text-xs font-medium">解析：</span>
                              <textarea className="w-full text-xs p-1 border rounded bg-background resize-none" rows={2}
                                value={cardResult.explanation || ""}
                                onChange={(e) => setCardResult({ ...cardResult, explanation: e.target.value })} />
                            </div>
                            {cardResult.categories && cardResult.categories.length > 0 && (
                              <div><span className="text-xs font-medium">分类：</span>
                                <select className="text-xs p-1 border rounded bg-background ml-1"
                                  value={cardResult.category_id || ""}
                                  onChange={(e) => setCardResult({ ...cardResult, category_id: e.target.value ? parseInt(e.target.value) : null, category_name: cardResult.categories.find((c: any) => c.id === parseInt(e.target.value))?.name || "" })}>
                                  <option value="">自动</option>
                                  {cardResult.categories.map((c: any) => (
                                    <option key={c.id} value={c.id}>{c.name}</option>
                                  ))}
                                </select>
                                {cardResult.category_name && <span className="text-xs ml-1 text-muted-foreground">({cardResult.category_name})</span>}
                              </div>
                            )}
                          </div>
                          <div className="flex gap-2 mt-2">
                            <Button size="sm" onClick={handleSavePreviewCard} disabled={cardCreating} className="flex-1">
                              {cardCreating ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />保存中...</> : <><CheckCircle2 className="h-3 w-3 mr-1" />确认保存</>}
                            </Button>
                            <Button size="sm" variant="outline" onClick={handleCreateCard} disabled={cardCreating}>
                              🔄 重新生成
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="text-green-700 dark:text-green-400 space-y-1">
                          <p>✅ 卡片已创建！分类：{cardResult.category || "未分类"}</p>
                          <p className="text-xs"><strong>正面：</strong>{cardResult.front}</p>
                          <p className="text-xs"><strong>背面：</strong>{cardResult.back}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Related cards from this article */}
            {relatedCards.length > 0 && (
              <div className="bg-card rounded-xl border">
                <button
                  className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium hover:bg-muted/50 transition-colors"
                  onClick={() => setShowRelatedCards(!showRelatedCards)}
                >
                  <span className="flex items-center gap-2">
                    <Layers className="h-4 w-4 text-primary" />
                    本文关联卡片 ({relatedCards.length})
                  </span>
                  <span className={`transition-transform ${showRelatedCards ? "rotate-180" : ""}`}>▾</span>
                </button>
                {showRelatedCards && (
                  <div className="border-t px-5 py-3 space-y-2">
                    {relatedCards.map((card: any) => {
                      const isExpanded = expandedCardId === card.id;
                      const visibleTags = card.tags_list?.filter((tag: any) => !isHiddenTag(tag.name)) || [];
                      return (
                        <div
                          key={card.id}
                          className="rounded-lg border text-sm hover:bg-muted/30 transition-colors cursor-pointer"
                          onClick={() => setExpandedCardId(isExpanded ? null : card.id)}
                        >
                          <div className="flex items-start gap-2 px-3 py-2">
                            <span className={`transition-transform text-xs text-muted-foreground mt-0.5 shrink-0 ${isExpanded ? "rotate-90" : ""}`}>▸</span>
                            <div className="flex-1 min-w-0">
                              {/* Category + Tags */}
                              <div className="flex flex-wrap gap-1 mb-1">
                                {card.category_name && (
                                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                                    📂 {card.category_name}
                                  </Badge>
                                )}
                                {visibleTags.map((tag: any) => (
                                  <Badge
                                    key={tag.id}
                                    className="text-[10px] px-1.5 py-0"
                                    style={{ backgroundColor: tag.color || '#6366f1', color: '#fff' }}
                                  >
                                    {tag.name}
                                  </Badge>
                                ))}
                              </div>
                              <span className={`font-medium ${isExpanded ? "" : "line-clamp-2"}`}>{card.front}</span>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 shrink-0 text-destructive hover:text-destructive"
                              title="删除此卡片"
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (!token || !confirm("确定删除此卡片？")) return;
                                try {
                                  await reading.deleteArticleCard(detail.id, card.id, token);
                                  setRelatedCards((prev: any[]) => prev.filter((c: any) => c.id !== card.id));
                                } catch (err: any) {
                                  showToast(err.message || "删除失败", "error");
                                }
                              }}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                          {isExpanded && (
                            <div className="border-t px-3 py-3" onClick={(e) => e.stopPropagation()}>
                              <CardDetailPanel card={card} />
                              {token && <CardTagManager cardId={card.id} token={token} onTagsChange={(tags) => {
                                setRelatedCards((prev: any[]) => prev.map((c: any) =>
                                  c.id === card.id ? { ...c, tags_list: tags } : c
                                ));
                              }} />}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* AI Chat Panel */}
        {showChat && (
          <div className="fixed inset-0 z-50 bg-card md:static md:inset-auto md:z-auto md:w-[380px] md:shrink-0 md:h-full">
            <ArticleChat
              title={detail.title}
              content={detail.content}
              onClose={() => setShowChat(false)}
            />
          </div>
        )}
      </div>
    );
  }

  /* ── External link loading (e.g. from tag-detail page) ── */
  if (cameFromExternal && !detail) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  /* ── List View ── */
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BookMarked className="h-6 w-6" /> 文章精读
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            AI驱动的时政文章深度阅读分析 · 共 {total} 篇
          </p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Button variant="outline" size="sm" className="text-xs sm:text-sm" onClick={async () => {
            if (!token) return;
            try {
              const res = await reading.batchArchive(7, token);
              if (res.archived > 0) {
                showToast(`已归档 ${res.archived} 篇文章`, "success");
                fetchList();
              } else {
                showToast("没有需要归档的文章", "info");
              }
            } catch { /* ignore */ }
          }}>
            <Archive className="h-4 w-4 sm:mr-1" /> <span className="hidden sm:inline">自动归档</span>
          </Button>
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4 sm:mr-1" /> <span className="hidden sm:inline">添加文章</span>
          </Button>
          <Button variant="outline" size="sm" className="text-xs sm:text-sm" onClick={async () => {
            if (!token) return;
            try {
              const res = await reading.exportArticles(token);
              if (!res.ok) { showToast("导出失败", "error"); return; }
              const blob = await res.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `articles_${new Date().toISOString().slice(0,10)}.json`;
              a.click();
              URL.revokeObjectURL(url);
            } catch { showToast("导出失败", "error"); }
          }}>
            📥 <span className="hidden sm:inline">导出文章</span>
          </Button>
          <Button variant="outline" size="sm" className="text-xs sm:text-sm" onClick={() => {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = ".json";
            input.onchange = async (e) => {
              const file = (e.target as HTMLInputElement).files?.[0];
              if (!file || !token) return;
              try {
                const res = await reading.importArticles(file, token);
                alert(`导入完成：新增 ${res.imported || 0} 篇，跳过 ${res.skipped || 0} 篇`);
                fetchList();
              } catch (err: any) { alert(err.message || "导入失败"); }
            };
            input.click();
          }}>
            📤 <span className="hidden sm:inline">导入文章</span>
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <Button
            size="sm"
            variant={statusFilter === null ? "default" : "outline"}
            onClick={() => { setStatusFilter(null); setPage(1); }}
          >
            全部
          </Button>
          {Object.entries(STATUS_LABELS).map(([key, { text, icon }]) => (
            <Button
              key={key}
              size="sm"
              variant={statusFilter === key ? "default" : "outline"}
              onClick={() => { setStatusFilter(key); setPage(1); }}
            >
              {icon}
              <span className="ml-1">{text}</span>
            </Button>
          ))}
          <div className="h-4 w-px bg-border mx-1" />
          <Button
            size="sm"
            variant={starredOnly ? "default" : "outline"}
            onClick={() => { setStarredOnly(!starredOnly); setPage(1); }}
          >
            <Star className="h-3.5 w-3.5 mr-1" /> 收藏
          </Button>
          <Button
            size="sm"
            variant={failedOnly ? "default" : "outline"}
            className={failedOnly ? "bg-red-600 hover:bg-red-700" : "text-red-600 border-red-200"}
            onClick={() => { setFailedOnly(!failedOnly); setPage(1); }}
          >
            ⚠️ 分析失败
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Search */}
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              className="pl-8 h-8 text-sm"
              placeholder="搜索标题..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { setPage(1); fetchList(); } }}
            />
          </div>
          {/* Source filter */}
          {sourceNames.length > 0 && (
            <select
              className="h-8 rounded-md border bg-background px-2 text-sm"
              value={sourceFilter || ""}
              onChange={(e) => { setSourceFilter(e.target.value || null); setPage(1); }}
            >
              <option value="">全部来源</option>
              {sourceNames.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}
          {/* Tag filter */}
          {filterTags.length > 0 && (
            <select
              className="h-8 rounded-md border bg-background px-2 text-sm"
              value={tagFilter || ""}
              onChange={(e) => { setTagFilter(e.target.value ? parseInt(e.target.value) : null); setPage(1); }}
            >
              <option value="">全部标签</option>
              {filterTags.map((t: any) => (
                <option key={t.id} value={t.id}>🏷️ {t.name}</option>
              ))}
            </select>
          )}
          {/* Sort */}
          <div className="flex items-center gap-1 ml-auto">
            <select
              className="h-8 rounded-md border bg-background px-2 text-sm"
              value={sortBy}
              onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
            >
              <option value="created_at">添加时间</option>
              <option value="publish_date">发布日期</option>
              <option value="quality_score">质量评分</option>
              <option value="word_count">字数</option>
            </select>
            <button
              className="h-8 w-8 flex items-center justify-center rounded-md border bg-background hover:bg-muted transition-colors"
              onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
              title={sortDir === "desc" ? "降序" : "升序"}
            >
              {sortDir === "desc" ? <ArrowDown className="h-3.5 w-3.5" /> : <ArrowUp className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-card rounded-xl border p-6 space-y-4">
          <h3 className="font-semibold">添加文章进行精读分析</h3>
          {/* URL auto-fill */}
          <div className="flex gap-2">
            <div className="flex-1 flex gap-2">
              <Globe className="h-4 w-4 mt-2.5 text-muted-foreground shrink-0" />
              <Input
                placeholder="输入文章URL，自动填充标题、来源等信息"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleFetchUrl(); }}
              />
            </div>
            <Button
              variant="outline"
              onClick={handleFetchUrl}
              disabled={fetchingUrl || !urlInput.trim()}
            >
              {fetchingUrl ? (
                <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> 获取中...</>
              ) : (
                <><Globe className="h-4 w-4 mr-1" /> 自动填充</>
              )}
            </Button>
          </div>
          <Input
            placeholder="文章标题"
            value={createForm.title}
            onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <Input
              placeholder="来源名称（如：人民日报）"
              value={createForm.source_name}
              onChange={(e) => setCreateForm((f) => ({ ...f, source_name: e.target.value }))}
            />
            <Input
              placeholder="来源URL"
              value={createForm.source_url}
              onChange={(e) => setCreateForm((f) => ({ ...f, source_url: e.target.value }))}
            />
            <Input
              type="date"
              placeholder="发布日期"
              value={createForm.publish_date}
              onChange={(e) => setCreateForm((f) => ({ ...f, publish_date: e.target.value }))}
            />
          </div>
          <textarea
            className="w-full min-h-[200px] rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            placeholder="粘贴文章全文内容..."
            value={createForm.content}
            onChange={(e) => setCreateForm((f) => ({ ...f, content: e.target.value }))}
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => { setShowCreate(false); setUrlInput(""); }}>取消</Button>
            <Button
              variant="outline"
              onClick={() => handleCreate(false)}
              disabled={creating || !createForm.title.trim() || !createForm.content.trim()}
            >
              {creating && creatingMode === "analysis" ? (
                <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> AI分析中...</>
              ) : (
                <><FileText className="h-4 w-4 mr-1" /> 仅精读分析</>
              )}
            </Button>
            <Button
              onClick={() => handleCreate(true)}
              disabled={creating || !createForm.title.trim() || !createForm.content.trim()}
            >
              {creating && creatingMode === "cards" ? (
                <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> 分析 + 生成卡片中...</>
              ) : (
                <><FileStack className="h-4 w-4 mr-1" /> 精读 + 生成卡片</>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <BookMarked className="h-12 w-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg font-medium">暂无精读文章</p>
          <p className="text-sm mt-1">手动添加文章，或运行文章管道自动生成精读分析</p>
        </div>
      ) : (
        <div className="space-y-2">
          {/* Batch operations bar */}
          {items.length > 0 && (
            <div className="flex items-center gap-2 py-2 px-1">
              <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={selectedIds.size === items.length && items.length > 0}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedIds(new Set(items.map((i) => i.id)));
                    } else {
                      setSelectedIds(new Set());
                    }
                  }}
                />
                全选
              </label>
              {selectedIds.size > 0 && (
                <>
                  <span className="text-xs text-muted-foreground">已选 {selectedIds.size} 篇</span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    disabled={batchReanalyzing}
                    onClick={async () => {
                      if (!token || selectedIds.size === 0) return;
                      setBatchReanalyzing(true);
                      try {
                        const res = await reading.batchReanalyze(Array.from(selectedIds), token);
                        alert(`重新分析完成：成功 ${res.success} 篇，失败 ${res.failed} 篇`);
                        fetchList();
                      } catch (e: any) {
                        alert("批量分析失败：" + (e.message || "未知错误"));
                      } finally {
                        setBatchReanalyzing(false);
                      }
                    }}
                  >
                    {batchReanalyzing ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Sparkles className="h-3 w-3 mr-1" />}
                    批量分析
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs text-red-600 border-red-200"
                    onClick={async () => {
                      if (!token || selectedIds.size === 0) return;
                      if (!confirm(`确定删除选中的 ${selectedIds.size} 篇文章？`)) return;
                      try {
                        const res = await reading.batchDelete(Array.from(selectedIds), token);
                        alert(`已删除 ${res.deleted} 篇文章`);
                        fetchList();
                      } catch (e: any) {
                        alert("批量删除失败：" + (e.message || "未知错误"));
                      }
                    }}
                  >
                    <Trash2 className="h-3 w-3 mr-1" /> 批量删除
                  </Button>
                </>
              )}
            </div>
          )}
          {items.map((item) => {
            const sl = STATUS_LABELS[item.status] || STATUS_LABELS.new;
            return (
              <div
                key={item.id}
                className="bg-card rounded-lg border p-4 hover:shadow-sm transition-shadow cursor-pointer group"
                onClick={() => openDetail(item.id)}
              >
                <div className="flex items-start gap-3">
                  <label className="flex items-center mt-1" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      className="rounded"
                      checked={selectedIds.has(item.id)}
                      onChange={(e) => {
                        const next = new Set(selectedIds);
                        if (e.target.checked) next.add(item.id);
                        else next.delete(item.id);
                        setSelectedIds(next);
                      }}
                    />
                  </label>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-medium text-sm truncate">{item.title}</h3>
                      {item.is_starred && (
                        <Star className="h-3.5 w-3.5 fill-yellow-400 text-yellow-400 flex-shrink-0" />
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${sl.color}`}>
                        {sl.icon} {sl.text}
                      </span>
                      <QualityBadge score={item.quality_score} />
                      {item.source_name && <span>{item.source_name}</span>}
                      {item.publish_date && <span>{item.publish_date}</span>}
                      <span>{item.word_count} 字</span>
                      <span>{formatDateTime(item.created_at, { dateOnly: true })}</span>
                    </div>
                    {/* Article tags */}
                    {item.tags_list && item.tags_list.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1 mt-1.5">
                        {item.tags_list.map((tag) => (
                          <Badge
                            key={tag.id}
                            className="text-[10px] px-1.5 py-0"
                            style={{ backgroundColor: tag.color || '#6366f1', color: '#fff' }}
                          >
                            {tag.name}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {item.source_url && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={(e) => { e.stopPropagation(); window.open(item.source_url, "_blank"); }}
                        title="打开原文链接"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8"
                      onClick={(e) => { e.stopPropagation(); toggleStar(item.id, item.is_starred); }}
                      title={item.is_starred ? "取消收藏" : "收藏"}
                    >
                      {item.is_starred ? (
                        <Star className="h-4 w-4 fill-yellow-400 text-yellow-400" />
                      ) : (
                        <StarOff className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-destructive"
                      onClick={(e) => { e.stopPropagation(); handleDelete(item.id); }}
                      title="删除文章"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</Button>
          <span className="flex items-center text-sm text-muted-foreground px-3">{page} / {totalPages}</span>
          <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>下一页</Button>
        </div>
      )}

      {/* Toast notification */}
      {toast && (
        <div className={cn(
          "fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-lg shadow-lg text-sm font-medium transition-all animate-in slide-in-from-bottom-4 fade-in duration-300",
          toast.type === "success" && "bg-green-600 text-white",
          toast.type === "error" && "bg-red-600 text-white",
          toast.type === "info" && "bg-blue-600 text-white",
        )}>
          {toast.type === "success" && "✅ "}{toast.type === "error" && "❌ "}{toast.message}
        </div>
      )}
    </div>
  );
}
