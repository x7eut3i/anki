"use client";

import { useEffect, useState, useMemo } from "react";
import { useAuthStore } from "@/lib/store";
import { cards as cardApi, decks as deckApi, categories as catApi, ai as aiApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Trash2,
  Send,
  ArrowLeft,
  Copy,
  ChevronDown,
  ChevronUp,
  Loader2,
  Sparkles,
  CheckCircle2,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

/* ── Dynamic fields per category ── */
const CATEGORY_FIELDS: Record<string, { key: string; label: string; required?: boolean; placeholder: string }[]> = {
  "成语": [
    { key: "front", label: "成语", required: true, placeholder: "输入成语（四字）" },
  ],
  "实词辨析": [
    { key: "front", label: "语境句", required: true, placeholder: "输入包含横线的语境句" },
    { key: "back", label: "正确词语", placeholder: "正确答案" },
  ],
  "规范词": [
    { key: "front", label: "口语说法", required: true, placeholder: "输入口语/白话说法" },
    { key: "back", label: "规范表述", placeholder: "对应的公文规范表述" },
  ],
  "金句/名言": [
    { key: "front", label: "金句（挖空）", required: true, placeholder: "完整金句，将关键词替换为______" },
    { key: "back", label: "关键词", placeholder: "被挖空的关键词" },
  ],
  "古诗词名句": [
    { key: "front", label: "诗句（挖空）", required: true, placeholder: "诗句填空" },
    { key: "back", label: "答案", placeholder: "被挖空的词/句" },
  ],
};

const DEFAULT_FIELDS = [
  { key: "front", label: "题目 / 正面", required: true, placeholder: "输入问题或提示..." },
  { key: "back", label: "答案 / 背面", required: false, placeholder: "输入答案（选填，AI可自动填写）" },
  { key: "explanation", label: "解析", required: false, placeholder: "输入详细解析（选填）" },
  { key: "distractors", label: "干扰项（逗号分隔）", required: false, placeholder: "干扰项A, 干扰项B, 干扰项C（选填）" },
];

interface CardDraft {
  id: number;
  front: string;
  back: string;
  explanation: string;
  distractors: string;
  tags: string;
  expanded: boolean;
}

function newDraft(id: number): CardDraft {
  return { id, front: "", back: "", explanation: "", distractors: "", tags: "", expanded: true };
}

export default function CreateCardsPage() {
  const { token } = useAuthStore();
  const [cats, setCats] = useState<any[]>([]);
  const [decksList, setDecksList] = useState<any[]>([]);
  const [selectedDeckId, setSelectedDeckId] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<CardDraft[]>([newDraft(1)]);
  const [nextId, setNextId] = useState(2);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: number; total: number; aiEnriched?: number } | null>(null);
  const [aiProgress, setAiProgress] = useState("");
  const [aiRefine, setAiRefine] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" | "info" } | null>(null);

  const showToast = (message: string, type: "success" | "error" | "info" = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 5000);
  };

  useEffect(() => {
    if (!token) return;
    Promise.all([catApi.list(token), deckApi.list(token)]).then(([c, d]) => {
      setCats(c);
      setDecksList(d);
    });
  }, [token]);

  // Filter out AI-XXX decks
  const availableDecks = useMemo(
    () => decksList.filter((d) => !d.name.startsWith("AI-")),
    [decksList]
  );

  // Get the category name for the selected deck
  const selectedDeckCatName = useMemo(() => {
    if (!selectedDeckId) return "";
    const deck = decksList.find((d) => d.id === selectedDeckId);
    if (!deck || !deck.category_id) return "";
    const cat = cats.find((c) => c.id === deck.category_id);
    return cat?.name || "";
  }, [selectedDeckId, decksList, cats]);

  // Get the fields to show based on category
  const fields = useMemo(() => {
    if (selectedDeckCatName && CATEGORY_FIELDS[selectedDeckCatName]) {
      return CATEGORY_FIELDS[selectedDeckCatName];
    }
    return DEFAULT_FIELDS;
  }, [selectedDeckCatName]);

  const updateDraft = (id: number, field: keyof CardDraft, value: any) => {
    setDrafts((prev) =>
      prev.map((d) => (d.id === id ? { ...d, [field]: value } : d))
    );
  };

  const addDraft = () => {
    // Collapse all other drafts
    setDrafts((prev) => [
      ...prev.map((d) => ({ ...d, expanded: false })),
      newDraft(nextId),
    ]);
    setNextId((n) => n + 1);
  };

  const removeDraft = (id: number) => {
    setDrafts((prev) => prev.filter((d) => d.id !== id));
  };

  const duplicateDraft = (id: number) => {
    const source = drafts.find((d) => d.id === id);
    if (!source) return;
    const dup: CardDraft = { ...source, id: nextId, expanded: true };
    const idx = drafts.findIndex((d) => d.id === id);
    const next = [...drafts];
    next.splice(idx + 1, 0, dup);
    // Collapse others
    setDrafts(next.map((d) => ({ ...d, expanded: d.id === nextId ? true : false })));
    setNextId((n) => n + 1);
  };

  const toggleExpand = (id: number) => {
    updateDraft(id, "expanded", !drafts.find((d) => d.id === id)?.expanded);
  };

  // Valid = has front content
  const validDrafts = drafts.filter((d) => d.front.trim());

  const handleSubmit = async () => {
    if (!token || !selectedDeckId || validDrafts.length === 0) return;
    setSubmitting(true);
    setResult(null);
    setAiProgress("");

    try {
      const deck = decksList.find((d) => d.id === selectedDeckId);
      const catId = deck?.category_id || null;
      const catName = selectedDeckCatName;

      // Build cards data for async processing
      const cardsData = validDrafts.map((d) => {
        const distractorsRaw = d.distractors.trim();
        let distractorsStr = distractorsRaw;
        if (distractorsRaw && !distractorsRaw.startsWith("[")) {
          const list = distractorsRaw.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
          distractorsStr = list.length > 0 ? JSON.stringify(list) : "";
        }
        return {
          front: d.front.trim(),
          back: d.back.trim(),
          explanation: d.explanation.trim(),
          distractors: distractorsStr,
          tags: d.tags.trim(),
          category: catName || "",
        };
      });

      // Check if any cards need AI completion
      const needsAI = cardsData.some((c) => !c.back);
      // AI refine: even if all cards have back, user opted in for AI enrichment
      const useAI = needsAI || aiRefine;

      if (useAI) {
        // Use async endpoint - AI completion + card creation in background
        const resp = await aiApi.completeCardsAsync(
          { cards: cardsData, deck_id: selectedDeckId, category_id: catId, allow_correction: aiRefine },
          token
        );
        showToast(
          `✅ 已提交 ${cardsData.length} 张卡片，AI 正在后台补全内容并创建卡片。可在「AI 统计」页查看进度。`,
          "success"
        );
        // Clear submitted drafts
        setDrafts([newDraft(nextId)]);
        setNextId((n) => n + 1);
      } else {
        // All cards have back content - create directly (no AI needed)
        setAiProgress("正在保存卡片...");
        const finalCards = cardsData.map((c) => ({
          deck_id: selectedDeckId,
          category_id: catId,
          front: c.front,
          back: c.back,
          explanation: c.explanation,
          distractors: c.distractors,
          tags: c.tags,
          card_type: c.distractors ? "choice" : "qa",
        }));
        const resp = await cardApi.bulkCreate(finalCards, token);
        const created = resp?.created || finalCards.length;
        setResult({ success: created, total: finalCards.length });
        showToast(`✅ 成功创建 ${created} 张卡片`, "success");
        setDrafts([newDraft(nextId)]);
        setNextId((n) => n + 1);
      }
    } catch (err: any) {
      console.error("Submit failed:", err);
      showToast("提交失败: " + (err.message || "未知错误"), "error");
    } finally {
      setSubmitting(false);
      setAiProgress("");
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href="/decks">
          <Button variant="ghost" size="icon" title="返回卡组列表">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h2 className="text-3xl font-bold tracking-tight">手动添加卡片</h2>
          <p className="text-muted-foreground">
            只需填写题目，AI 自动补充答案、解析和干扰项
          </p>
        </div>
      </div>

      {/* Step 1: Select deck */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">📂 选择牌组</CardTitle>
        </CardHeader>
        <CardContent>
          {availableDecks.length === 0 ? (
            <p className="text-sm text-muted-foreground">没有可用的牌组，请先创建牌组</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
              {availableDecks.map((d) => {
                const cat = cats.find((c: any) => c.id === d.category_id);
                const isSelected = selectedDeckId === d.id;
                return (
                  <button
                    key={d.id}
                    onClick={() => setSelectedDeckId(d.id)}
                    className={cn(
                      "flex flex-col items-start gap-1 p-3 rounded-lg border-2 text-left transition-all text-sm",
                      isSelected
                        ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                        : "border-muted hover:border-primary/40 hover:bg-muted/50"
                    )}
                  >
                    <span className={cn("font-medium truncate w-full", isSelected ? "text-primary" : "")}>
                      {d.name}
                    </span>
                    <div className="flex items-center gap-1.5 w-full">
                      {cat && (
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {cat.name}
                        </Badge>
                      )}
                      <span className="text-[10px] text-muted-foreground ml-auto">
                        {d.card_count || 0}张
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          {selectedDeckCatName && (
            <p className="text-xs text-muted-foreground mt-2">
              <Sparkles className="inline h-3 w-3 mr-1" />
              检测到分类「{selectedDeckCatName}」，已调整输入项。提交后 AI 将自动补充完整内容。
            </p>
          )}
        </CardContent>
      </Card>

      {/* Step 2: Card drafts */}
      {selectedDeckId && (
        <>
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">
              📝 卡片内容 ({validDrafts.length}/{drafts.length} 张有效)
            </h3>
            <Button variant="outline" size="sm" onClick={addDraft}>
              <Plus className="mr-1 h-4 w-4" />
              添加卡片
            </Button>
          </div>

          <div className="space-y-3">
            {drafts.map((draft, idx) => (
              <Card
                key={draft.id}
                className={cn(
                  "transition-colors",
                  draft.front.trim()
                    ? "border-green-200 dark:border-green-800"
                    : ""
                )}
              >
                <div
                  className="flex items-center justify-between px-4 py-3 cursor-pointer"
                  onClick={() => toggleExpand(draft.id)}
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-sm font-medium text-muted-foreground">
                      #{idx + 1}
                    </span>
                    {draft.front.trim() ? (
                      <span className="text-sm truncate">{draft.front}</span>
                    ) : (
                      <span className="text-sm text-muted-foreground italic">未填写</span>
                    )}
                    {draft.front.trim() && (
                      <Badge variant="secondary" className="text-xs bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                        ✓
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    {draft.expanded ? (
                      <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                </div>

                {draft.expanded && (
                  <CardContent className="pt-0 space-y-3">
                    {fields.map((f) => (
                      <div key={f.key}>
                        <label className="text-xs font-medium text-muted-foreground">
                          {f.label} {f.required && <span className="text-red-500">*</span>}
                        </label>
                        {f.key === "explanation" ? (
                          <textarea
                            placeholder={f.placeholder}
                            value={(draft as any)[f.key] || ""}
                            onChange={(e) => updateDraft(draft.id, f.key as keyof CardDraft, e.target.value)}
                            className="w-full mt-1 p-2 rounded-md border border-input bg-background text-sm min-h-[40px] resize-y"
                          />
                        ) : f.key === "front" || f.key === "back" ? (
                          <textarea
                            placeholder={f.placeholder}
                            value={(draft as any)[f.key] || ""}
                            onChange={(e) => updateDraft(draft.id, f.key as keyof CardDraft, e.target.value)}
                            className="w-full mt-1 p-2 rounded-md border border-input bg-background text-sm min-h-[60px] resize-y"
                          />
                        ) : (
                          <Input
                            placeholder={f.placeholder}
                            value={(draft as any)[f.key] || ""}
                            onChange={(e) => updateDraft(draft.id, f.key as keyof CardDraft, e.target.value)}
                            className="mt-1"
                          />
                        )}
                      </div>
                    ))}

                    {/* Actions */}
                    <div className="flex gap-2 flex-wrap pt-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => duplicateDraft(draft.id)}
                      >
                        <Copy className="mr-1 h-4 w-4" />
                        复制
                      </Button>
                      {drafts.length > 1 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() => removeDraft(draft.id)}
                        >
                          <Trash2 className="mr-1 h-4 w-4" />
                          删除
                        </Button>
                      )}
                    </div>
                  </CardContent>
                )}
              </Card>
            ))}
          </div>

          {/* Add more & submit */}
          <div className="flex items-center justify-between">
            <Button variant="outline" onClick={addDraft}>
              <Plus className="mr-1 h-4 w-4" />
              继续添加
            </Button>

            <div className="flex items-center gap-3">
              {/* AI refine checkbox – hidden for idiom category (always uses AI) */}
              {selectedDeckCatName !== "成语" && (
                <label className="flex items-center gap-1.5 cursor-pointer text-sm select-none">
                  <input
                    type="checkbox"
                    checked={aiRefine}
                    onChange={(e) => setAiRefine(e.target.checked)}
                    className="rounded border-input h-4 w-4 accent-primary"
                  />
                  <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                  <span className="text-muted-foreground">允许AI修正</span>
                </label>
              )}
              {result && (
                <span className="text-sm text-green-600">
                  ✅ 成功创建 {result.success} 张卡片
                  {result.aiEnriched ? `，AI 已补充 ${result.aiEnriched} 张` : ""}
                </span>
              )}
              {aiProgress && (
                <span className="text-sm text-blue-600 flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  {aiProgress}
                </span>
              )}
              <Button
                onClick={handleSubmit}
                disabled={submitting || validDrafts.length === 0 || !selectedDeckId}
                className="min-w-[120px]"
              >
                {submitting ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-1 h-4 w-4" />
                )}
                {submitting
                  ? "处理中..."
                  : `提交 ${validDrafts.length} 张卡片`}
              </Button>
            </div>
          </div>

          {/* Instructions */}
          <div className="bg-muted/50 rounded-lg p-4 text-sm text-muted-foreground space-y-1">
            <p className="font-medium text-foreground">💡 使用说明</p>
            <p>• 只需填写题目（正面），其余字段AI会自动补充</p>
            <p>• 提交后AI会自动在后台生成答案、解析和干扰项（异步处理）</p>
            <p>• 如果你已经知道答案，可以手动填写，AI将跳过已填字段</p>
            <p>• 选择不同分类的牌组，输入项会自动调整（如成语只需输入四字成语名）</p>
            <p>• 提交后可在「<Link href="/ai-stats" className="text-primary underline">AI 统计</Link>」页面查看任务进度</p>
          </div>
        </>
      )}

      {/* Toast notification */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4">
          <div className={cn(
            "flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg border text-sm max-w-md",
            toast.type === "success" && "bg-green-50 text-green-800 border-green-200",
            toast.type === "error" && "bg-red-50 text-red-800 border-red-200",
            toast.type === "info" && "bg-blue-50 text-blue-800 border-blue-200",
          )}>
            {toast.type === "success" && <CheckCircle2 className="h-4 w-4 shrink-0" />}
            <span>{toast.message}</span>
            <button onClick={() => setToast(null)} className="ml-2 shrink-0 opacity-60 hover:opacity-100">✕</button>
          </div>
        </div>
      )}
    </div>
  );
}
