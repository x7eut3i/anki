"use client";

import { useEffect, useState, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { decks as deckApi, cards as cardApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  BookOpen,
  Trash2,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  CheckSquare,
  Square,
  Search,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  CardDetailPanel,
  CardHeaderBadges,
  CardTagManager,
  knowledgeTypeLabel,
  fsrsStateLabel,
  parseJson,
} from "@/components/card-detail";

export default function DeckDetailPage() {
  const { token } = useAuthStore();
  const params = useSearchParams();
  const router = useRouter();
  const deckId = params.get("id");

  const [deck, setDeck] = useState<any>(null);
  const [cards, setCards] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());
  const [expandAll, setExpandAll] = useState(false);

  // Batch selection
  const [selectedCards, setSelectedCards] = useState<Set<number>>(new Set());
  const [batchMode, setBatchMode] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Sorting
  type SortKey = "default" | "front" | "created_at" | "state" | "reps";
  type SortDir = "asc" | "desc";
  const [sortKey, setSortKey] = useState<SortKey>("default");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  // Search & filter
  const [searchQuery, setSearchQuery] = useState("");
  const [stateFilter, setStateFilter] = useState<string>("all");

  useEffect(() => {
    if (!token || !deckId) return;
    const id = parseInt(deckId);
    if (isNaN(id)) {
      setLoading(false);
      return;
    }
    const loadData = async () => {
      try {
        const d = await deckApi.get(id, token);
        setDeck(d);
      } catch (err) {
        console.error("Failed to load deck:", err);
      }
      try {
        // Load all cards in pages of 200 (backend max)
        let allCards: any[] = [];
        let page = 1;
        const PAGE_SIZE = 200;
        while (true) {
          const c = await cardApi.list({ deck_id: id, page, page_size: PAGE_SIZE }, token);
          const batch = c.cards || [];
          allCards = allCards.concat(batch);
          if (batch.length < PAGE_SIZE || allCards.length >= c.total) break;
          page++;
        }
        setCards(allCards);
      } catch (err) {
        console.error("Failed to load cards:", err);
      }
      setLoading(false);
    };
    loadData();
  }, [token, deckId]);

  // Filtered & sorted cards
  const sortedCards = useMemo(() => {
    let filtered = cards;
    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      filtered = filtered.filter(
        (c) =>
          (c.front || "").toLowerCase().includes(q) ||
          (c.back || "").toLowerCase().includes(q) ||
          (c.explanation || "").toLowerCase().includes(q)
      );
    }
    // State filter
    if (stateFilter !== "all") {
      const st = parseInt(stateFilter);
      filtered = filtered.filter((c) => c.state === st);
    }
    if (sortKey === "default") return filtered;
    const sorted = [...filtered].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "front":
          cmp = (a.front || "").localeCompare(b.front || "", "zh-CN");
          break;
        case "created_at":
          cmp = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
          break;
        case "state":
          cmp = (a.state || 0) - (b.state || 0);
          break;
        case "reps":
          cmp = (a.reps || 0) - (b.reps || 0);
          break;
      }
      return sortDir === "desc" ? -cmp : cmp;
    });
    return sorted;
  }, [cards, sortKey, sortDir, searchQuery, stateFilter]);

  const toggleCard = (cardId: number) => {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(cardId)) {
        next.delete(cardId);
      } else {
        next.add(cardId);
      }
      return next;
    });
  };

  const toggleExpandAll = () => {
    if (expandAll) {
      setExpandedCards(new Set());
    } else {
      setExpandedCards(new Set(cards.map((c) => c.id)));
    }
    setExpandAll(!expandAll);
  };

  const toggleSelectCard = (cardId: number) => {
    setSelectedCards((prev) => {
      const next = new Set(prev);
      if (next.has(cardId)) next.delete(cardId);
      else next.add(cardId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedCards.size === sortedCards.length) {
      setSelectedCards(new Set());
    } else {
      setSelectedCards(new Set(sortedCards.map((c) => c.id)));
    }
  };

  const handleDeleteCard = async (cardId: number) => {
    if (!token || !confirm("确定删除此卡片？")) return;
    await cardApi.delete(cardId, token);
    setCards(cards.filter((c) => c.id !== cardId));
    setExpandedCards((prev) => {
      const next = new Set(prev);
      next.delete(cardId);
      return next;
    });
    setSelectedCards((prev) => {
      const next = new Set(prev);
      next.delete(cardId);
      return next;
    });
  };

  const handleBatchDelete = async () => {
    if (!token || selectedCards.size === 0) return;
    if (!confirm(`确定删除选中的 ${selectedCards.size} 张卡片？此操作不可撤销。`)) return;
    setDeleting(true);
    try {
      await deckApi.batchDeleteCards(Array.from(selectedCards), token);
      setCards(cards.filter((c) => !selectedCards.has(c.id)));
      setSelectedCards(new Set());
      setBatchMode(false);
    } catch (err) {
      console.error("Batch delete failed:", err);
      alert("批量删除失败，请重试");
    } finally {
      setDeleting(false);
    }
  };

  const sortLabels: Record<SortKey, string> = {
    default: "默认",
    front: "题面",
    created_at: "创建时间",
    state: "学习状态",
    reps: "复习次数",
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!deck) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <p className="text-muted-foreground">牌组不存在</p>
        <Link href="/decks">
          <Button variant="outline">
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回牌组列表
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/decks">
            <Button variant="ghost" size="icon" title="返回卡组列表">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h2 className="text-3xl font-bold tracking-tight">{deck.name}</h2>
            <p className="text-muted-foreground">{deck.description || "暂无描述"}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Link href={`/study?deck=${deckId}`}>
            <Button>
              <BookOpen className="mr-2 h-4 w-4" />
              开始学习
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{cards.length}</div>
            <p className="text-xs text-muted-foreground">总卡片数</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">
              {cards.filter((c) => c.state === 0).length}
            </div>
            <p className="text-xs text-muted-foreground">新卡片</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">
              {cards.filter((c) => new Date(c.due) <= new Date()).length}
            </div>
            <p className="text-xs text-muted-foreground">待复习</p>
          </CardContent>
        </Card>
      </div>

      {/* Cards list */}
      <Card>
        <CardHeader className="flex flex-col gap-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-lg">卡片列表 ({sortedCards.length}/{cards.length})</CardTitle>
            <div className="flex gap-2 flex-wrap">
              {/* Batch mode toggle */}
              {cards.length > 0 && (
                <Button
                  variant={batchMode ? "default" : "ghost"}
                  size="sm"
                  onClick={() => {
                    setBatchMode(!batchMode);
                    if (batchMode) setSelectedCards(new Set());
                  }}
                >
                  <CheckSquare className="mr-1 h-4 w-4" />
                  {batchMode ? "退出批量" : "批量操作"}
                </Button>
              )}

              {cards.length > 0 && (
                <Button variant="ghost" size="sm" onClick={toggleExpandAll}>
                  {expandAll ? (
                    <><EyeOff className="mr-1 h-4 w-4" /> 收起全部</>
                  ) : (
                    <><Eye className="mr-1 h-4 w-4" /> 展开全部</>
                  )}
                </Button>
              )}
            </div>
          </div>

          {/* Search & filter bar */}
          {cards.length > 0 && (
            <div className="flex flex-wrap gap-2 items-center">
              {/* Search */}
              <div className="relative flex-1 min-w-[200px]">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="搜索卡片内容..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full h-9 pl-8 pr-3 rounded-md border border-input bg-background text-sm"
                />
              </div>

              {/* State filter */}
              <select
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value)}
                className="h-9 px-3 rounded-md border border-input bg-background text-sm"
              >
                <option value="all">全部状态</option>
                <option value="0">🆕 新卡</option>
                <option value="1">📖 学习中</option>
                <option value="2">✅ 复习</option>
                <option value="3">🔄 重学</option>
              </select>

              {/* Sort */}
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className="h-9 px-3 rounded-md border border-input bg-background text-sm"
              >
                <option value="default">默认排序</option>
                <option value="front">题面</option>
                <option value="created_at">创建时间</option>
                <option value="state">学习状态</option>
                <option value="reps">复习次数</option>
              </select>
              {sortKey !== "default" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-9 px-2"
                  onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
                  title={sortDir === "asc" ? "切换为降序" : "切换为升序"}
                >
                  {sortDir === "asc" ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
                </Button>
              )}
            </div>
          )}
        </CardHeader>

        {/* Batch action bar */}
        {batchMode && (
          <div className="px-6 pb-3 flex items-center gap-3 border-b">
            <Button variant="ghost" size="sm" onClick={toggleSelectAll}>
              {selectedCards.size === sortedCards.length ? (
                <><CheckSquare className="mr-1 h-4 w-4" /> 取消全选</>
              ) : (
                <><Square className="mr-1 h-4 w-4" /> 全选</>
              )}
            </Button>
            <span className="text-sm text-muted-foreground">
              已选 {selectedCards.size} / {sortedCards.length}
            </span>
            {selectedCards.size > 0 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={handleBatchDelete}
                disabled={deleting}
              >
                <Trash2 className="mr-1 h-4 w-4" />
                {deleting ? "删除中..." : `删除 ${selectedCards.size} 张`}
              </Button>
            )}
          </div>
        )}

        <CardContent>
          {cards.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              这个牌组还没有卡片
            </div>
          ) : (
            <div className="space-y-2">
              {sortedCards.map((card) => {
                const isExpanded = expandedCards.has(card.id);
                const isSelected = selectedCards.has(card.id);
                const distractors = parseJson(card.distractors, []);
                const meta = parseJson<Record<string, any> | null>(card.meta_info, null);
                return (
                  <div
                    key={card.id}
                    className={cn(
                      "rounded-lg border transition-colors",
                      isExpanded ? "bg-muted/30 border-primary/30" : "hover:bg-muted/50",
                      isSelected && batchMode ? "ring-2 ring-destructive/50 bg-red-50 dark:bg-red-950/10" : ""
                    )}
                  >
                    {/* Card header row */}
                    <div
                      className="flex items-start justify-between p-4 cursor-pointer"
                      onClick={() => batchMode ? toggleSelectCard(card.id) : toggleCard(card.id)}
                    >
                      <div className="flex items-start gap-2 flex-1 min-w-0">
                        {/* Checkbox in batch mode */}
                        {batchMode && (
                          <div className="mt-0.5">
                            {isSelected ? (
                              <CheckSquare className="h-5 w-5 text-destructive" />
                            ) : (
                              <Square className="h-5 w-5 text-muted-foreground" />
                            )}
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <CardHeaderBadges card={card} />
                          {meta?.subject && (
                            <p className="text-xs text-muted-foreground mb-0.5">📌 {meta.subject}</p>
                          )}
                          <p className={cn(
                            "font-medium text-sm",
                            isExpanded ? "" : "line-clamp-2"
                          )}>
                            {card.front}
                          </p>
                        </div>
                      </div>
                      <div className="flex gap-1 ml-2 items-center">
                        {!batchMode && (
                          <>
                            {isExpanded ? (
                              <ChevronUp className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <ChevronDown className="h-4 w-4 text-muted-foreground" />
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-destructive"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteCard(card.id);
                              }}
                              title="删除卡片"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Expanded detail */}
                    {isExpanded && !batchMode && (
                      <div className="px-4 pb-4">
                        <CardDetailPanel card={card} />
                        <CardTagManager cardId={card.id} token={token!} onTagsChange={(tags) => {
                          setCards((prev) => prev.map((c) => c.id === card.id ? { ...c, tags_list: tags } : c));
                        }} />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
