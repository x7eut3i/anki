"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { useAuthStore } from "@/lib/store";
import { saveSortPreference, loadSortPreference } from "@/lib/sort-preferences";
import { decks as deckApi, categories as catApi, cards as cardsApi, tags as tagsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Trash2,
  Edit2,
  Library,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Search,
  ArrowUp,
  ArrowDown,
  Tag,
  X,
  CheckSquare,
  Square,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { CardDetailPanel, CardHeaderBadges, parseJson } from "@/components/card-detail";
import { HighlightText } from "@/components/highlight-text";
import { CardEditModal } from "@/components/card-edit-modal";
import { Pencil } from "lucide-react";

export default function DecksPage() {
  const { token } = useAuthStore();
  const [decksList, setDecksList] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newCatId, setNewCatId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [allTags, setAllTags] = useState<any[]>([]);
  const [tagFilter, setTagFilter] = useState<string>("all");

  // Search state - no debounce, manual trigger
  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [expandedSearchCard, setExpandedSearchCard] = useState<number | null>(null);
  const [searchBatchMode, setSearchBatchMode] = useState(false);
  const [selectedSearchCards, setSelectedSearchCards] = useState<Set<number>>(new Set());
  const [editingSearchCard, setEditingSearchCard] = useState<any | null>(null);

  // Sort & filter
  type SortKey = "name" | "card_count" | "created_at";
  type SortDir = "asc" | "desc";
  const [sortKey, setSortKey] = useState<SortKey>(() => loadSortPreference("decks", { sortKey: "name", sortDir: "asc" }).sortKey as SortKey);
  const [sortDir, setSortDir] = useState<SortDir>(() => loadSortPreference("decks", { sortKey: "name", sortDir: "asc" }).sortDir as SortDir);
  const [searchQuery, setSearchQuery] = useState("");
  const [catFilter, setCatFilter] = useState<string>("all");

  // Persist sort preferences
  useEffect(() => {
    saveSortPreference("decks", { sortKey, sortDir });
  }, [sortKey, sortDir]);

  const loadDecks = async (query?: string) => {
    if (!token) return;
    setLoading(true);
    try {
      const [d, c, t] = await Promise.all([
        deckApi.list(token, query || undefined),
        catApi.list(token),
        tagsApi.list(token),
      ]);
      setDecksList(d);
      setCats(c);
      setAllTags(t);
    } finally {
      setLoading(false);
    }
  };

  // Explicit search (no debounce)
  const handleSearch = async () => {
    const q = searchQuery.trim();
    const hasTagFilter = tagFilter !== "all";
    const hasCatFilter = catFilter !== "all";
    if (!q && !hasTagFilter && !hasCatFilter) {
      setSearchResults(null);
      setExpandedSearchCard(null);
      return;
    }
    if (!token) return;
    setSearchLoading(true);
    try {
      const params: Record<string, any> = { page_size: 50 };
      if (q) params.search = q;
      if (hasCatFilter) {
        const cid = parseInt(catFilter);
        if (cid > 0) params.category_id = cid;
      }
      if (hasTagFilter) params.tag_id = parseInt(tagFilter);
      const data = await cardsApi.list(params, token);
      setSearchResults(data.cards || []);
      setExpandedSearchCard(null);
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  };

  const clearSearch = () => {
    setSearchQuery("");
    setSearchResults(null);
    setExpandedSearchCard(null);
    setSearchBatchMode(false);
    setSelectedSearchCards(new Set());
  };

  const handleDeleteSearchCard = async (cardId: number) => {
    if (!token || !confirm("确定删除此卡片？此操作不可撤销。")) return;
    try {
      await cardsApi.delete(cardId, token);
      setSearchResults((prev) => prev ? prev.filter((c) => c.id !== cardId) : null);
    } catch (e) { console.error("Delete failed:", e); }
  };

  const handleBatchDeleteSearchCards = async () => {
    if (!token || selectedSearchCards.size === 0) return;
    if (!confirm(`确定删除选中的 ${selectedSearchCards.size} 张卡片？此操作不可撤销。`)) return;
    try {
      await deckApi.batchDeleteCards(Array.from(selectedSearchCards), token);
      setSearchResults((prev) => prev ? prev.filter((c) => !selectedSearchCards.has(c.id)) : null);
      setSelectedSearchCards(new Set());
      setSearchBatchMode(false);
    } catch (e) { console.error("Batch delete failed:", e); }
  };

  const toggleSearchSelect = (cardId: number) => {
    setSelectedSearchCards((prev) => {
      const next = new Set(prev);
      if (next.has(cardId)) next.delete(cardId);
      else next.add(cardId);
      return next;
    });
  };

  // Re-search when filters change
  useEffect(() => {
    const hasFilter = catFilter !== "all" || tagFilter !== "all";
    if (searchResults !== null || hasFilter) {
      handleSearch();
    }
  }, [catFilter, tagFilter]);

  useEffect(() => { loadDecks(); }, [token]);

  const handleCreate = async () => {
    if (!token || !newName.trim()) return;
    await deckApi.create(
      { name: newName, description: newDesc, category_id: newCatId },
      token
    );
    setNewName("");
    setNewDesc("");
    setNewCatId(null);
    setShowCreate(false);
    loadDecks();
  };

  const handleDelete = async (id: number) => {
    if (!token || !confirm("确定删除此牌组？其中所有卡片也会被删除。")) return;
    await deckApi.delete(id, token);
    loadDecks();
  };

  const getCatName = (catId: number) =>
    cats.find((c) => c.id === catId)?.name || "";

  const getCatIcon = (catId: number) =>
    cats.find((c) => c.id === catId)?.icon || "📚";

  // Filtered & sorted decks
  const sortedDecks = useMemo(() => {
    let filtered = decksList;
    if (catFilter !== "all") {
      const cid = parseInt(catFilter);
      if (cid === 0) {
        filtered = filtered.filter((d) => !d.category_id);
      } else {
        filtered = filtered.filter((d) => d.category_id === cid);
      }
    }
    const sorted = [...filtered].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "name":
          cmp = (a.name || "").localeCompare(b.name || "", "zh-CN");
          break;
        case "card_count":
          cmp = (a.card_count || 0) - (b.card_count || 0);
          break;
        case "created_at":
          cmp = new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime();
          break;
      }
      return sortDir === "desc" ? -cmp : cmp;
    });
    return sorted;
  }, [decksList, sortKey, sortDir, searchQuery, catFilter]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">牌组管理</h2>
          <p className="text-muted-foreground">管理你的学习牌组和卡片</p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="mr-2 h-4 w-4" />
          新建牌组
        </Button>
      </div>

      {/* Create form */}
      {showCreate && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <Input
              placeholder="牌组名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <Input
              placeholder="描述 (可选)"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />
            <div>
              <p className="text-sm font-medium mb-2">选择分类</p>
              <div className="flex flex-wrap gap-2">
                {cats.map((cat) => (
                  <Badge
                    key={cat.id}
                    variant={newCatId === cat.id ? "default" : "outline"}
                    className="cursor-pointer"
                    onClick={() => setNewCatId(cat.id)}
                  >
                    {cat.icon} {cat.name}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={!newName.trim()}>
                创建
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Search, filter & sort bar */}
      {decksList.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <div className="relative flex-1 min-w-[200px] flex gap-1">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="搜索卡片内容..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="w-full h-9 pl-8 pr-3 rounded-md border border-input bg-background text-sm"
              />
            </div>
            <Button size="sm" className="h-9" onClick={handleSearch} disabled={searchLoading}>
              搜索
            </Button>
            {searchResults !== null && (
              <Button size="sm" variant="outline" className="h-9" onClick={clearSearch}>
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>
          <select
            value={catFilter}
            onChange={(e) => setCatFilter(e.target.value)}
            className="h-9 px-3 rounded-md border border-input bg-background text-sm"
          >
            <option value="all">全部分类</option>
            <option value="0">未分类</option>
            {cats.map((c) => (
              <option key={c.id} value={c.id}>
                {c.icon} {c.name}
              </option>
            ))}
          </select>
          {allTags.length > 0 && (
            <select
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              className="h-9 px-3 rounded-md border border-input bg-background text-sm"
            >
              <option value="all">全部标签</option>
              {allTags.map((t: any) => (
                <option key={t.id} value={t.id}>
                  🏷️ {t.name}
                </option>
              ))}
            </select>
          )}
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as SortKey)}
            className="h-9 px-3 rounded-md border border-input bg-background text-sm"
          >
            <option value="name">按名称</option>
            <option value="card_count">按卡片数</option>
            <option value="created_at">按创建时间</option>
          </select>
          <Button
            variant="outline"
            size="sm"
            className="h-9 px-2"
            onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
          >
            {sortDir === "asc" ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
          </Button>
        </div>
      )}

      {/* Search results - card list with full detail */}
      {searchResults !== null && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                搜索结果 ({searchResults.length} 张卡片)
                {catFilter !== "all" && <span className="text-xs font-normal text-muted-foreground ml-2">· 分类筛选中</span>}
                {tagFilter !== "all" && <span className="text-xs font-normal text-muted-foreground ml-2">· 标签筛选中</span>}
              </CardTitle>
              <div className="flex items-center gap-2">
                {searchBatchMode && selectedSearchCards.size > 0 && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleBatchDeleteSearchCards}
                  >
                    <Trash2 className="h-3 w-3 mr-1" />
                    删除 ({selectedSearchCards.size})
                  </Button>
                )}
                <Button
                  variant={searchBatchMode ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setSearchBatchMode(!searchBatchMode);
                    setSelectedSearchCards(new Set());
                  }}
                >
                  {searchBatchMode ? "完成" : "批量管理"}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {searchLoading ? (
              <div className="flex justify-center py-8">
                <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
              </div>
            ) : searchResults.length === 0 ? (
              <p className="text-muted-foreground text-center py-4">没有找到匹配的卡片</p>
            ) : (
              <div className="space-y-2 max-h-[70vh] overflow-y-auto">
                {searchBatchMode && searchResults.length > 0 && (
                  <div className="flex items-center gap-2 mb-2 text-sm">
                    <button
                      className="text-primary hover:underline text-xs"
                      onClick={() => {
                        if (selectedSearchCards.size === searchResults.length) {
                          setSelectedSearchCards(new Set());
                        } else {
                          setSelectedSearchCards(new Set(searchResults.map((c: any) => c.id)));
                        }
                      }}
                    >
                      {selectedSearchCards.size === searchResults.length ? "取消全选" : "全选"}
                    </button>
                    <span className="text-muted-foreground text-xs">已选 {selectedSearchCards.size} 张</span>
                  </div>
                )}
                {searchResults.map((card: any) => {
                  const isExpanded = expandedSearchCard === card.id;
                  const isSelected = selectedSearchCards.has(card.id);
                  const deckName = decksList.find((d) => d.id === card.deck_id)?.name;
                  const meta = parseJson<Record<string, any> | null>(card.meta_info, null);
                  return (
                    <div
                      key={card.id}
                      className={cn(
                        "rounded-lg border transition-colors",
                        isExpanded ? "bg-muted/30 border-primary/30" : "hover:bg-muted/50",
                        isSelected && searchBatchMode ? "ring-2 ring-destructive/50 bg-red-50 dark:bg-red-950/10" : ""
                      )}
                    >
                      {/* Card header */}
                      <div
                        className="flex items-start justify-between p-3 cursor-pointer"
                        onClick={() => searchBatchMode ? toggleSearchSelect(card.id) : setExpandedSearchCard(isExpanded ? null : card.id)}
                      >
                        <div className="flex items-start gap-2 flex-1 min-w-0">
                          {searchBatchMode && (
                            <div className="mt-0.5">
                              {isSelected ? (
                                <CheckSquare className="h-5 w-5 text-destructive" />
                              ) : (
                                <Square className="h-5 w-5 text-muted-foreground" />
                              )}
                            </div>
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                              <CardHeaderBadges card={card} />
                              {deckName && (
                                <Badge variant="secondary" className="text-xs">
                                  📚 {deckName}
                                </Badge>
                              )}
                            </div>
                            {meta?.subject && (
                              <p className="text-xs text-muted-foreground mb-0.5">📌 {meta.subject}</p>
                            )}
                            <p className={cn("text-sm font-medium", isExpanded ? "" : "line-clamp-2")}>
                              <HighlightText text={card.front} query={searchQuery.trim()} />
                            </p>
                            {!isExpanded && card.back && (
                              <p className="text-xs text-muted-foreground truncate mt-0.5">
                                <HighlightText text={card.back} query={searchQuery.trim()} />
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 ml-2">
                          {!searchBatchMode && (
                            <>
                              {isExpanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingSearchCard(card);
                                }}
                                title="编辑卡片"
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-destructive"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteSearchCard(card.id);
                                }}
                                title="删除卡片"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Expanded card detail — reuses shared CardDetailPanel */}
                      {isExpanded && !searchBatchMode && (
                        <div className="px-3 pb-3">
                          <CardDetailPanel card={card} searchQuery={searchQuery.trim()} />
                          <div className="mt-2 flex justify-end">
                            <Link
                              href={`/deck-detail?id=${card.deck_id}`}
                              className="text-xs text-primary hover:underline flex items-center"
                            >
                              打开牌组 <ChevronRight className="h-3 w-3 ml-0.5" />
                            </Link>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Decks grid */}
      {sortedDecks.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <Library className="h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground">
              {decksList.length === 0 ? "还没有牌组，创建一个开始学习吧" : "没有匹配的牌组"}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {sortedDecks.map((deck) => (
            <Card key={deck.id} className="hover:shadow-md transition-shadow">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-base">{deck.name}</CardTitle>
                    {deck.category_id && (
                      <Badge variant="secondary" className="text-xs mt-1">
                        {getCatIcon(deck.category_id)} {getCatName(deck.category_id)}
                      </Badge>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive"
                    onClick={() => handleDelete(deck.id)}
                    title="删除卡组"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="pb-3">
                <p className="text-sm text-muted-foreground">
                  {deck.description || "暂无描述"}
                </p>
                <p className="text-sm mt-2">
                  <span className="font-medium">{deck.card_count || 0}</span>{" "}
                  张卡片
                </p>
                {(deck.card_count > 0) && (
                  <div className="flex gap-3 mt-1.5 text-xs text-muted-foreground">
                    <span className="text-blue-600">待学 {deck.new_count ?? 0}</span>
                    <span className="text-amber-600">学习中 {deck.learning_count ?? 0}</span>
                    <span className="text-green-600">已掌握 {deck.mastered_count ?? 0}</span>
                  </div>
                )}
              </CardContent>
              <CardFooter className="pt-0">
                <Link
                  href={`/deck-detail?id=${deck.id}`}
                  className="text-sm text-primary hover:underline flex items-center"
                >
                  查看卡片
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      {/* Card Edit Modal for search results */}
      {editingSearchCard && token && (
        <CardEditModal
          card={editingSearchCard}
          token={token}
          onSaved={(updated) => {
            setSearchResults((prev) =>
              prev ? prev.map((c) => c.id === editingSearchCard.id ? { ...c, ...updated } : c) : null
            );
            setEditingSearchCard(null);
          }}
          onClose={() => setEditingSearchCard(null)}
        />
      )}
    </div>
  );
}
