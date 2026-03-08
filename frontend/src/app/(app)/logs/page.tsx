"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useAuthStore } from "@/lib/store";
import { logs } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Search,
  RefreshCw,
  FileText,
  ChevronLeft,
  ChevronRight,
  Bot,
  Monitor,
  AlertCircle,
  Info,
  Bug,
  AlertTriangle,
  Trash2,
  Calendar,
  Settings,
} from "lucide-react";

const LEVEL_COLORS: Record<string, string> = {
  ERROR: "text-red-500 bg-red-500/10",
  WARNING: "text-yellow-500 bg-yellow-500/10",
  INFO: "text-blue-500 bg-blue-500/10",
  DEBUG: "text-gray-400 bg-gray-400/10",
};

const LEVEL_ICONS: Record<string, React.ReactNode> = {
  ERROR: <AlertCircle className="h-3.5 w-3.5" />,
  WARNING: <AlertTriangle className="h-3.5 w-3.5" />,
  INFO: <Info className="h-3.5 w-3.5" />,
  DEBUG: <Bug className="h-3.5 w-3.5" />,
};

/** Individual log entry with ref-based overflow detection */
function LogEntry({ entry, idx, isExpanded, hasMultiLine, hasExtra, activeTab, onToggle }: {
  entry: any; idx: number; isExpanded: boolean; hasMultiLine: boolean;
  hasExtra: boolean; activeTab: "ai" | "app"; onToggle: () => void;
}) {
  const messageRef = useRef<HTMLSpanElement>(null);
  const [isTruncated, setIsTruncated] = useState(false);

  useEffect(() => {
    const el = messageRef.current;
    if (!el || isExpanded) return;
    const check = () => setIsTruncated(el.scrollWidth > el.clientWidth);
    check();
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [entry.message, isExpanded]);

  const isExpandable = hasExtra || (activeTab === "app" && (isTruncated || hasMultiLine));

  return (
    <div className="px-4 py-2 hover:bg-muted/50 text-sm">
      <div
        className={`flex items-center gap-2 ${isExpandable ? "cursor-pointer" : ""}`}
        onClick={() => isExpandable && onToggle()}
      >
        <span className="text-xs text-muted-foreground font-mono whitespace-nowrap">
          {formatDateTime(entry.timestamp)}
        </span>
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${LEVEL_COLORS[entry.level] || "text-gray-500"}`}>
          {LEVEL_ICONS[entry.level]}
          {entry.level}
        </span>
        <span
          ref={messageRef}
          className={`flex-1 font-mono text-xs ${isExpanded ? "whitespace-pre-wrap break-all" : "truncate"}`}
        >
          {hasMultiLine && !isExpanded ? entry.message.split("\n")[0] + " ..." : entry.message}
        </span>
        {isExpandable && (
          <span className="text-xs text-muted-foreground shrink-0">
            {isExpanded ? "▼" : "▶"}
          </span>
        )}
      </div>
      {isExpanded && (
        <div className="mt-2 space-y-2" onClick={(e) => e.stopPropagation()}>
          {(hasMultiLine || (activeTab === "app" && isTruncated)) && !entry.data && (
            <pre className="p-3 bg-muted rounded-md text-xs overflow-x-auto max-h-96 whitespace-pre-wrap break-all">
              {entry.message}
            </pre>
          )}
          {entry.data && (
            <pre className="p-3 bg-muted rounded-md text-xs overflow-x-auto max-h-96 whitespace-pre-wrap break-all">
              {JSON.stringify(entry.data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function LogsPage() {
  const { token } = useAuthStore();
  const [activeTab, setActiveTab] = useState<"ai" | "app">("ai");
  const [entries, setEntries] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [expandedAppIds, setExpandedAppIds] = useState<Set<number>>(new Set());
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [retentionDays, setRetentionDays] = useState(0);
  const [retentionInput, setRetentionInput] = useState("");
  const [retentionSaving, setRetentionSaving] = useState(false);
  const [showRetention, setShowRetention] = useState(false);

  const fetchDates = useCallback(async () => {
    if (!token) return;
    try {
      const dates = await logs.getDates(activeTab, token);
      setAvailableDates(dates || []);
    } catch (e) {
      console.error("Failed to fetch dates:", e);
    }
  }, [token, activeTab]);

  const fetchRetention = useCallback(async () => {
    if (!token) return;
    try {
      const data = await logs.getRetention(token);
      setRetentionDays(data.retention_days ?? 0);
      setRetentionInput(String(data.retention_days ?? 0));
    } catch (e) {
      console.error("Failed to fetch retention:", e);
    }
  }, [token]);

  const saveRetention = async () => {
    if (!token) return;
    setRetentionSaving(true);
    try {
      const days = Math.max(0, parseInt(retentionInput) || 0);
      const data = await logs.setRetention(days, token);
      setRetentionDays(data.retention_days ?? 0);
      setRetentionInput(String(data.retention_days ?? 0));
      if (data.cleanup && Object.keys(data.cleanup).length > 0) {
        fetchLogs();
        fetchDates();
      }
    } catch (e) {
      console.error("Failed to save retention:", e);
    } finally {
      setRetentionSaving(false);
    }
  };

  const fetchLogs = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await logs.getEntries(activeTab, {
        search, level, page, page_size: pageSize, date: dateFilter || undefined,
      }, token);
      setEntries(data.entries || []);
      setTotal(data.total || 0);
    } catch (e) {
      console.error("Failed to fetch logs:", e);
    } finally {
      setLoading(false);
    }
  }, [token, activeTab, search, level, page, pageSize, dateFilter]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    fetchDates();
  }, [fetchDates]);

  useEffect(() => {
    fetchRetention();
  }, [fetchRetention]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(fetchLogs, 5000);
    return () => clearInterval(timer);
  }, [autoRefresh, fetchLogs]);

  const handleClear = async () => {
    if (!token || !confirm(`确定要清空 ${activeTab === "ai" ? "AI交互" : "应用"} 日志吗？`)) return;
    try {
      await logs.clear(activeTab, token);
      fetchLogs();
      fetchDates();
    } catch (e) {
      console.error("Failed to clear log:", e);
    }
  };

  const toggleExpand = (idx: number) => {
    setExpandedIds((prev) => {
      if (prev.has(idx)) {
        // Clicking same header: collapse it
        return new Set();
      }
      // Clicking a different entry: expand it (collapses previous)
      return new Set([idx]);
    });
  };

  const toggleAppExpand = (idx: number) => {
    setExpandedAppIds((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const totalPages = Math.ceil(total / pageSize);

  const tabs = [
    { id: "ai" as const, label: "AI交互日志", icon: Bot },
    { id: "app" as const, label: "应用日志", icon: Monitor },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 shrink-0">
          <FileText className="h-5 w-5 sm:h-6 sm:w-6" /> 日志查看器
        </h1>
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowRetention(!showRetention)}
          >
            <Settings className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">日志保留</span>
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleClear}
          >
            <Trash2 className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">清空日志</span>
          </Button>
          <Button
            variant={autoRefresh ? "default" : "outline"}
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            <RefreshCw className={`h-4 w-4 sm:mr-1 ${autoRefresh ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">{autoRefresh ? "停止" : "自动刷新"}</span>
          </Button>
          <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* Retention settings */}
      {showRetention && (
        <Card>
          <CardContent className="py-3 px-4">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm font-medium">自动删除超过</span>
              <Input
                type="number"
                min={0}
                className="w-24"
                value={retentionInput}
                onChange={(e) => setRetentionInput(e.target.value)}
                placeholder="0"
              />
              <span className="text-sm text-muted-foreground">天的日志</span>
              <Button size="sm" onClick={saveRetention} disabled={retentionSaving}>
                {retentionSaving ? "保存中..." : "保存"}
              </Button>
              <span className="text-xs text-muted-foreground ml-2">
                {retentionDays > 0
                  ? `当前设置：保留最近 ${retentionDays} 天`
                  : "当前设置：永久保留（0 = 不自动删除）"}
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-muted rounded-lg w-fit">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => { setActiveTab(tab.id); setPage(1); setExpandedIds(new Set()); setExpandedAppIds(new Set()); setDateFilter(""); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="搜索日志内容..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          />
        </div>
        <select
          className="border rounded-md px-3 py-2 text-sm bg-background"
          value={level}
          onChange={(e) => { setLevel(e.target.value); setPage(1); }}
        >
          <option value="">全部级别</option>
          <option value="ERROR">ERROR</option>
          <option value="WARNING">WARNING</option>
          <option value="INFO">INFO</option>
          <option value="DEBUG">DEBUG</option>
        </select>
        <select
          className="border rounded-md px-3 py-2 text-sm bg-background"
          value={dateFilter}
          onChange={(e) => { setDateFilter(e.target.value); setPage(1); }}
        >
          <option value="">全部日期</option>
          {availableDates.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      {/* Log entries */}
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            共 {total} 条记录 · 第 {page}/{totalPages || 1} 页
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="divide-y max-h-[65vh] overflow-y-auto">
            {entries.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">
                {loading ? "加载中..." : "暂无日志"}
              </div>
            ) : (
              entries.map((entry, idx) => {
                const isExpanded = activeTab === "ai" ? expandedIds.has(idx) : expandedAppIds.has(idx);
                const hasMultiLine = entry.message && entry.message.includes("\n");
                const hasExtra = entry.data || hasMultiLine;
                return (
                <LogEntry
                  key={idx}
                  entry={entry}
                  idx={idx}
                  isExpanded={isExpanded}
                  hasMultiLine={hasMultiLine}
                  hasExtra={hasExtra}
                  activeTab={activeTab}
                  onToggle={() => {
                    if (activeTab === "ai" && hasExtra) {
                      toggleExpand(idx);
                    } else if (activeTab === "app") {
                      toggleAppExpand(idx);
                    }
                  }}
                />
                );
              })
            )}
          </div>
        </CardContent>
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
