"use client";

import React from "react";
import { Badge } from "@/components/ui/badge";
import { ExternalLink } from "lucide-react";
import { formatDateTime } from "@/lib/timezone";

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
  tags_list?: { id: number; name: string; color: string }[];
}

/**
 * Shared article list item component used by reading page and tag-detail page.
 * Renders article title, metadata, quality badge, external link icon.
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
  return (
    <div
      className={`bg-card rounded-lg border p-4 hover:shadow-sm hover:border-primary/40 transition-all cursor-pointer group ${className || ""}`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        {leftSlot}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium text-sm line-clamp-2">{article.title}</h3>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {article.source_name && <span>{article.source_name}</span>}
            {article.publish_date && <span>{article.publish_date}</span>}
            {article.word_count != null && article.word_count > 0 && (
              <span>{article.word_count}字</span>
            )}
            {article.quality_score != null && article.quality_score > 0 && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 font-medium">
                ⭐ {article.quality_score}
              </span>
            )}
            {article.created_at && (
              <span>{formatDateTime(article.created_at, { dateOnly: true })}</span>
            )}
          </div>
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
