"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { tags as tagsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  BookOpen,
  Layers,
  Loader2,
  Tag,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  ArrowUp,
  ArrowDown,
  Search,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { saveSortPreference, loadSortPreference } from "@/lib/sort-preferences";
import {
  CardDetailPanel,
  CardHeaderBadges,
} from "@/components/card-detail";
import { HighlightText } from "@/components/highlight-text";
import { ArticleListItem } from "@/components/article-list-item";

interface TagCard {
  id: number;
  front: string;
  back: string;
  explanation?: string;
  distractors?: string;
  meta_info?: string;
  tags?: string;
  tags_list?: { id: number; name: string; color: string }[];
  deck_name: string;
  category_name: string;
  is_ai_generated?: boolean;
  created_at: string;
}

interface TagArticle {
  id: number;
  title: string;
  content: string;
  analysis_html: string;
  source_url: string;
  source_name: string;
  publish_date: string;
  quality_score: number;
  quality_reason: string;
  word_count: number;
  status: string;
  created_at: string;
}

export default function TagDetailPage() {
  const { token } = useAuthStore();
  const router = useRouter();
  const params = useSearchParams();
  const tagId = params.get("id");
  const tagName = params.get("name") || "";
  const tagColor = params.get("color") || "#6B7280";

  const [loading, setLoading] = useState(true);
  const [cards, setCards] = useState<TagCard[]>([]);
  const [articles, setArticles] = useState<TagArticle[]>([]);
  const [activeTab, setActiveTab] = useState<"cards" | "articles">(
    (params.get("tab") as "cards" | "articles") || "cards"
  );

  // Card expand
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());
  const [expandAll, setExpandAll] = useState(false);

  // Sort, filter, search for cards
  type SortKey = "default" | "front" | "created_at" | "deck_name";
  type SortDir = "asc" | "desc";
  const [sortKey, setSortKey] = useState<SortKey>(() => loadSortPreference("tag-detail", { sortKey: "default", sortDir: "asc" }).sortKey as SortKey);
  const [sortDir, setSortDir] = useState<SortDir>(() => loadSortPreference("tag-detail", { sortKey: "default", sortDir: "asc" }).sortDir as SortDir);
  const [searchQuery, setSearchQuery] = useState("");

  // Persist sort preferences
  useEffect(() => {
    saveSortPreference("tag-detail", { sortKey, sortDir });
  }, [sortKey, sortDir]);

  // Filtered & sorted cards
  const sortedCards = useMemo(() => {
    let filtered = cards;
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      filtered = filtered.filter(
        (c) =>
          (c.front || "").toLowerCase().includes(q) ||
          (c.back || "").toLowerCase().includes(q) ||
          (c.explanation || "").toLowerCase().includes(q)
      );
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
        case "deck_name":
          cmp = (a.deck_name || "").localeCompare(b.deck_name || "", "zh-CN");
          break;
      }
      return sortDir === "desc" ? -cmp : cmp;
    });
    return sorted;
  }, [cards, sortKey, sortDir, searchQuery]);

  const loadDetail = useCallback(async () => {
    if (!token || !tagId) return;
    setLoading(true);
    try {
      const data = await tagsApi.detail(parseInt(tagId), token);
      setCards(data.cards || []);
      setArticles(data.articles || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, tagId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const toggleCard = (cardId: number) => {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(cardId)) next.delete(cardId);
      else next.add(cardId);
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

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/tags">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回
          </Button>
        </Link>
        <Badge
          className="text-lg px-4 py-1.5"
          style={{ backgroundColor: tagColor, color: "white" }}
        >
          🏷️ {tagName}
        </Badge>
        <span className="text-muted-foreground text-sm">
          {cards.length} 张卡片 · {articles.length} 篇文章
        </span>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b pb-2">
        <Button
          size="sm"
          variant={activeTab === "cards" ? "default" : "outline"}
          onClick={() => {
            setActiveTab("cards");
            const p = new URLSearchParams(params.toString());
            p.set("tab", "cards");
            window.history.replaceState(null, "", `?${p.toString()}`);
          }}
        >
          <Layers className="h-4 w-4 mr-1" />
          卡片 ({cards.length})
        </Button>
        <Button
          size="sm"
          variant={activeTab === "articles" ? "default" : "outline"}
          onClick={() => {
            setActiveTab("articles");
            const p = new URLSearchParams(params.toString());
            p.set("tab", "articles");
            window.history.replaceState(null, "", `?${p.toString()}`);
          }}
        >
          <BookOpen className="h-4 w-4 mr-1" />
          文章 ({articles.length})
        </Button>
        {/* Quick actions */}
        {activeTab === "cards" && cards.length > 0 && (
          <Link href={`/study?tag_ids=${tagId}`} className="ml-auto">
            <Button size="sm" variant="secondary">
              📖 基于此标签学习
            </Button>
          </Link>
        )}
      </div>

      {/* Cards tab - same display as deck-detail */}
      {activeTab === "cards" && (
        <div className="space-y-3">
          {cards.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
                <Tag className="h-12 w-12 text-muted-foreground opacity-30" />
                <p className="text-muted-foreground">该标签下暂无卡片</p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Toolbar: search, sort, expand */}
              <div className="space-y-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <span className="text-sm text-muted-foreground">
                    共 {sortedCards.length}/{cards.length} 张卡片
                  </span>
                  <Button variant="ghost" size="sm" onClick={toggleExpandAll}>
                    {expandAll ? (
                      <><EyeOff className="mr-1 h-4 w-4" /> 收起全部</>
                    ) : (
                      <><Eye className="mr-1 h-4 w-4" /> 展开全部</>
                    )}
                  </Button>
                </div>

                {/* Search & sort bar */}
                <div className="flex flex-wrap gap-2 items-center">
                  <div className="relative flex-1 min-w-[180px]">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="搜索卡片内容..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full h-9 pl-8 pr-3 rounded-md border border-input bg-background text-sm"
                    />
                  </div>
                  <select
                    value={sortKey}
                    onChange={(e) => setSortKey(e.target.value as SortKey)}
                    className="h-9 px-3 rounded-md border border-input bg-background text-sm"
                  >
                    <option value="default">默认排序</option>
                    <option value="front">题面</option>
                    <option value="created_at">创建时间</option>
                    <option value="deck_name">所属牌组</option>
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
              </div>

              {/* Card list */}
              {sortedCards.map((card) => {
                const isExpanded = expandedCards.has(card.id);
                return (
                  <div
                    key={card.id}
                    className={cn(
                      "rounded-lg border transition-colors",
                      isExpanded ? "bg-muted/30 border-primary/30" : "hover:bg-muted/50"
                    )}
                  >
                    <div
                      className="flex items-start justify-between p-4 cursor-pointer"
                      onClick={() => toggleCard(card.id)}
                    >
                      <div className="flex-1 min-w-0">
                        <CardHeaderBadges card={card} />
                        <p className={cn(
                          "font-medium text-sm mt-1",
                          isExpanded ? "" : "line-clamp-2"
                        )}>
                          <HighlightText text={card.front} query={searchQuery.trim()} />
                        </p>
                      </div>
                      <div className="flex gap-1 ml-2 items-center">
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        )}
                      </div>
                    </div>
                    {isExpanded && (
                      <div className="px-4 pb-4">
                        <CardDetailPanel card={card} searchQuery={searchQuery.trim()} />
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* Articles tab - link to reading page for two-column view */}
      {activeTab === "articles" && (
        <div className="space-y-3">
          {articles.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
                <BookOpen className="h-12 w-12 text-muted-foreground opacity-30" />
                <p className="text-muted-foreground">该标签下暂无文章</p>
              </CardContent>
            </Card>
          ) : (
            articles.map((article) => (
              <ArticleListItem
                key={article.id}
                article={article}
                onClick={() => router.push(`/reading?article_id=${article.id}`)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
