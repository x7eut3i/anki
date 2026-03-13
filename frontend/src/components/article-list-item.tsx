"use client";

import React from "react";
import { Badge } from "@/components/ui/badge";
import { ExternalLink, BookOpen, Sparkles, Archive } from "lucide-react";
import { formatDateTime } from "@/lib/timezone";

function formatReadingTimeShort(ms: number): string {
  if (!ms || ms < 1000) return "";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  if (h > 0) return `${h}h${m > 0 ? m + "m" : ""}`;
  if (m > 0) return `${m}分钟`;
  return `${totalSec}秒`;
}

const STATUS_LABELS: Record<string, { text: string; color: string; icon: React.ReactNode }> = {
  new: { text: "新", color: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400", icon: <Sparkles className="h-3 w-3" /> },
  reading: { text: "在读", color: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400", icon: <BookOpen className="h-3 w-3" /> },
  archived: { text: "归档", color: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400", icon: <Archive className="h-3 w-3" /> },
};

function QualityBadge({ score }: { score: number }) {
  if (!score || score <= 0) return null;
  let color = "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  if (score >= 9) color = "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400";
  else if (score >= 7) color = "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-400";
  else if (score >= 5) color = "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      ⭐ {score}/10
    </span>
  );
}

const ERROR_STATE = { CLEANUP_FAILED: 1, ANALYSIS_FAILED: 2, CARD_GEN_FAILED: 4 } as const;

function errorStateBadges(es: number) {
  const badges: { label: string; color: string }[] = [];
  if (es & ERROR_STATE.CLEANUP_FAILED) badges.push({ label: "清洗失败", color: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400" });
  if (es & ERROR_STATE.ANALYSIS_FAILED) badges.push({ label: "分析失败", color: "bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-400" });
  if (es & ERROR_STATE.CARD_GEN_FAILED) badges.push({ label: "生成卡片失败", color: "bg-yellow-100 text-yellow-700 dark:bg-yellow-950/40 dark:text-yellow-400" });
  return badges;
}

export interface ArticleItemData {
  id: number;
  title: string;
  source_url?: string;
  source_name?: string;
  publish_date?: string;
  quality_score?: number;
  word_count?: number;
  created_at?: string;
  status?: string;
  is_starred?: boolean;
  reading_time_ms?: number;
  card_count?: number;
  error_state?: number;
  tags_list?: { id: number; name: string; color: string }[];
}

/**
 * Shared article list item component.
 * 4-row layout: Title | Status row | Date row | Error row
 */
export function ArticleListItem({
  article,
  onClick,
  leftSlot,
  rightSlot,
  className,
}: {
  article: ArticleItemData;
  onClick?: () => void;
  leftSlot?: React.ReactNode;
  rightSlot?: React.ReactNode;
  className?: string;
}) {
  const sl = article.status ? (STATUS_LABELS[article.status] || STATUS_LABELS.new) : null;

  return (
    <div
      className={`bg-card rounded-lg border p-4 hover:shadow-sm hover:border-primary/40 transition-all cursor-pointer group ${className || ""}`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        {leftSlot}
        <div className="flex-1 min-w-0">
          {/* Row 1: Title */}
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium text-base line-clamp-2">{article.title}</h3>
          </div>

          {/* Row 2: Status — status badge, quality, source, word count, card count */}
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {sl && (
              <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${sl.color}`}>
                {sl.icon} {sl.text}
              </span>
            )}
            <QualityBadge score={article.quality_score ?? 0} />
            {article.source_name && <span>{article.source_name}</span>}
            {article.word_count != null && article.word_count > 0 && (
              <span>{article.word_count}字</span>
            )}
            {(article.card_count ?? 0) > 0 && (
              <span className="text-primary">🃏 {article.card_count} 张卡片</span>
            )}
          </div>

          {/* Row 3: Dates — publish date, created_at, reading time */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground mt-1">
            {article.publish_date && (
              <span>发布 <span className="font-medium">{formatDateTime(article.publish_date, { dateOnly: true })}</span></span>
            )}
            {article.created_at && (
              <span>收录 <span className="font-medium">{formatDateTime(article.created_at, { dateOnly: true })}</span></span>
            )}
            {(article.reading_time_ms ?? 0) > 0 && (
              <span>📖 已读 {formatReadingTimeShort(article.reading_time_ms!)}</span>
            )}
          </div>

          {/* Row 4: Error badges */}
          {(article.error_state ?? 0) > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 mt-1">
              {errorStateBadges(article.error_state!).map((b, i) => (
                <span key={i} className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium ${b.color}`}>
                  ⚠ {b.label}
                </span>
              ))}
            </div>
          )}

          {/* Tags */}
          {article.tags_list && article.tags_list.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 mt-1.5">
              {article.tags_list.map((tag) => (
                <Badge
                  key={tag.id}
                  className="text-[10px] px-1.5 py-0"
                  style={{ backgroundColor: tag.color || "#6366f1", color: "#fff" }}
                >
                  {tag.name}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          {article.source_url && (
            <span
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                window.open(article.source_url, "_blank");
              }}
              className="text-muted-foreground hover:text-primary transition-colors"
              title="打开原文链接"
            >
              <ExternalLink className="h-4 w-4" />
            </span>
          )}
          {rightSlot}
        </div>
      </div>
    </div>
  );
}
