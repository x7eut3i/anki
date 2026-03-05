"use client";

import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
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
  ExternalLink,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import {
  CardDetailPanel,
  CardHeaderBadges,
} from "@/components/card-detail";

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
        {cards.length > 0 && (
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
              {/* Toolbar */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  共 {cards.length} 张卡片
                </span>
                <Button variant="ghost" size="sm" onClick={toggleExpandAll}>
                  {expandAll ? (
                    <><EyeOff className="mr-1 h-4 w-4" /> 收起全部</>
                  ) : (
                    <><Eye className="mr-1 h-4 w-4" /> 展开全部</>
                  )}
                </Button>
              </div>

              {/* Card list */}
              {cards.map((card) => {
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
                          {card.front}
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
                        <CardDetailPanel card={card} />
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
              <Link
                key={article.id}
                href={`/reading?article_id=${article.id}`}
                prefetch={true}
              >
                <Card className="overflow-hidden hover:border-primary/40 transition-colors cursor-pointer">
                  <div className="flex items-center justify-between p-4">
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="font-medium text-sm line-clamp-2">
                        {article.title}
                      </div>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                        {article.source_name && <span>{article.source_name}</span>}
                        {article.word_count > 0 && <span>· {article.word_count}字</span>}
                        {article.created_at && (
                          <span>· {new Date(article.created_at).toLocaleDateString("zh-CN")}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 ml-2">
                      {article.quality_score > 0 && (
                        <Badge variant="secondary" className="text-xs">
                          质量 {article.quality_score}
                        </Badge>
                      )}
                      {article.source_url && (
                        <span
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            window.open(article.source_url, "_blank");
                          }}
                          className="text-muted-foreground hover:text-primary"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </span>
                      )}
                      <BookOpen className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </div>
                </Card>
              </Link>
            ))
          )}
        </div>
      )}
    </div>
  );
}
