"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/lib/store";
import { ingestion } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  Trash2,
  Settings,
  FileText,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  SkipForward,
  Info,
  Square,
  Ban,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface IngestionLog {
  id: number;
  run_type: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  sources_processed: number;
  articles_fetched: number;
  articles_analyzed: number;
  articles_skipped: number;
  cards_created: number;
  errors_count: number;
  log_detail: string;
  timezone: string;
}

interface LogEntry {
  time: string;
  level: string;
  source: string;
  message: string;
}

export default function IngestionPage() {
  const { token, user } = useAuthStore();
  const [config, setConfig] = useState<any>(null);
  const [logs, setLogs] = useState<IngestionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [expandedLog, setExpandedLog] = useState<number | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const isAdmin = user?.is_admin;

  const loadData = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [cfg, logsData] = await Promise.all([
        ingestion.getConfig(token),
        ingestion.getLogs(20, token),
      ]);
      setConfig(cfg);
      setLogs(logsData);
      // If any job is running, mark button state
      if (logsData.some((l: IngestionLog) => l.status === "running")) {
        setRunning(true);
      }
    } catch (err) {
      console.error("Failed to load ingestion data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [token]);

  // Poll for live stats when any log is still running
  useEffect(() => {
    const hasRunning = logs.some((l) => l.status === "running");
    if (!hasRunning || !token) return;
    const interval = setInterval(async () => {
      try {
        const logsData = await ingestion.getLogs(20, token);
        setLogs(logsData);
        // Auto-expand running log
        const runningLog = logsData.find((l: IngestionLog) => l.status === "running");
        if (runningLog && !expandedLog) {
          setExpandedLog(runningLog.id);
        }
        // Stop polling if nothing is running anymore
        if (!logsData.some((l: IngestionLog) => l.status === "running")) {
          setRunning(false);
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [logs.some((l) => l.status === "running"), token]);

  const handleSave = async () => {
    if (!token || !config) return;
    setSaving(true);
    try {
      // Derive is_enabled from schedule_type
      const payload = {
        ...config,
        is_enabled: (config.schedule_type || "off") !== "off",
      };
      const updated = await ingestion.updateConfig(payload, token);
      setConfig(updated);
    } catch (err: any) {
      alert("保存失败: " + (err.message || "未知错误"));
    } finally {
      setSaving(false);
    }
  };

  const handleRun = async () => {
    if (!token) return;
    setRunning(true);
    try {
      await ingestion.run(token);
      // Immediately reload logs — the new "running" entry should appear
      const logsData = await ingestion.getLogs(20, token);
      setLogs(logsData);
      if (logsData.length > 0) {
        setExpandedLog(logsData[0].id);
      }
      // Polling effect will track progress from here
    } catch (err: any) {
      const msg = err?.message || "未知错误";
      // 409 = already running
      if (msg.includes("已有抓取任务")) {
        alert(msg);
      } else {
        alert("抓取启动失败: " + msg);
      }
      setRunning(false);
    }
  };

  const handleCancel = async (logId: number) => {
    if (!token) return;
    setCancelling(true);
    try {
      await ingestion.cancel(logId, token);
      setConfirmCancelId(null);
      // Polling will pick up the status change
    } catch (err: any) {
      alert("取消失败: " + (err?.message || "未知错误"));
    } finally {
      setCancelling(false);
    }
  };

  const handleClearLogs = async () => {
    if (!token || !confirm("确认清除所有抓取日志？")) return;
    try {
      await ingestion.clearLogs(token);
      setLogs([]);
    } catch (err: any) {
      alert("清除失败: " + (err.message || "未知错误"));
    }
  };

  const parseLogEntries = (detail: string): LogEntry[] => {
    try {
      return JSON.parse(detail) || [];
    } catch {
      return [];
    }
  };

  const levelIcon = (level: string) => {
    switch (level) {
      case "error": return <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />;
      case "warn": return <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />;
      case "skip": return <SkipForward className="h-3.5 w-3.5 text-muted-foreground shrink-0" />;
      default: return <Info className="h-3.5 w-3.5 text-blue-500 shrink-0" />;
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">自动抓取</h2>
        <p className="text-muted-foreground">配置自动抓取参数，查看抓取日志</p>
      </div>

      {/* Config */}
      {isAdmin && config && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Settings className="h-4 w-4" />
              抓取配置
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Enable/Disable toggle */}
            <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30">
              <label className="flex items-center gap-3 cursor-pointer flex-1">
                <input
                  type="checkbox"
                  checked={(config.schedule_type || "off") !== "off"}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setConfig({ ...config, schedule_type: config._prev_schedule_type || "daily" });
                    } else {
                      setConfig({ ...config, _prev_schedule_type: config.schedule_type, schedule_type: "off" });
                    }
                  }}
                  className="h-5 w-5 rounded border-gray-300 text-primary"
                />
                <div>
                  <span className="text-sm font-medium">
                    {(config.schedule_type || "off") !== "off" ? "✅ 自动抓取已启用" : "⏸️ 自动抓取已停用"}
                  </span>
                  <p className="text-xs text-muted-foreground">
                    {(config.schedule_type || "off") !== "off" ? "系统将按照下方设置的频率自动抓取文章" : "勾选此项以启用定时自动抓取"}
                  </p>
                </div>
              </label>
            </div>

            {/* Schedule section */}
            <div className="space-y-3">
              <label className="text-sm font-medium">定时抓取</label>
              <div className="flex items-center gap-3">
                <select
                  className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                  value={config.schedule_type || "daily"}
                  onChange={(e) => setConfig({ ...config, schedule_type: e.target.value, schedule_days: "" })}
                >
                  <option value="off">不自动抓取</option>
                  <option value="daily">每天</option>
                  <option value="weekly">每周</option>
                </select>
                {(config.schedule_type || "daily") !== "off" && (
                  <div className="flex items-center gap-1">
                    <select
                      className="h-9 w-20 rounded-md border border-input bg-background px-2 text-sm"
                      value={config.schedule_hour ?? 6}
                      onChange={(e) => setConfig({ ...config, schedule_hour: parseInt(e.target.value) })}
                    >
                      {Array.from({ length: 24 }, (_, i) => (
                        <option key={i} value={i}>{String(i).padStart(2, "0")}时</option>
                      ))}
                    </select>
                    <span className="text-muted-foreground">:</span>
                    <select
                      className="h-9 w-20 rounded-md border border-input bg-background px-2 text-sm"
                      value={config.schedule_minute ?? 0}
                      onChange={(e) => setConfig({ ...config, schedule_minute: parseInt(e.target.value) })}
                    >
                      {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map((m) => (
                        <option key={m} value={m}>{String(m).padStart(2, "0")}分</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              {(config.schedule_type === "weekly") && (
                <div className="flex gap-2 flex-wrap">
                  {[
                    { key: "1", label: "一" },
                    { key: "2", label: "二" },
                    { key: "3", label: "三" },
                    { key: "4", label: "四" },
                    { key: "5", label: "五" },
                    { key: "6", label: "六" },
                    { key: "0", label: "日" },
                  ].map((day) => {
                    const selected = (config.schedule_days || "").split(",").filter(Boolean);
                    const isSelected = selected.includes(day.key);
                    return (
                      <button
                        key={day.key}
                        type="button"
                        className={cn(
                          "h-8 w-8 rounded-full text-sm font-medium border transition-colors",
                          isSelected
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-background text-foreground border-input hover:bg-muted"
                        )}
                        onClick={() => {
                          const days = selected.filter((d: string) => d !== day.key);
                          if (!isSelected) days.push(day.key);
                          days.sort();
                          setConfig({ ...config, schedule_days: days.join(",") });
                        }}
                      >
                        {day.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Other settings */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">时区</label>
                <select
                  className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={config.timezone || "Asia/Shanghai"}
                  onChange={(e) => setConfig({ ...config, timezone: e.target.value })}
                >
                  <option value="Asia/Shanghai">Asia/Shanghai (中国标准时间)</option>
                  <option value="Asia/Hong_Kong">Asia/Hong_Kong (香港时间)</option>
                  <option value="Asia/Taipei">Asia/Taipei (台北时间)</option>
                  <option value="Asia/Tokyo">Asia/Tokyo (东京时间)</option>
                  <option value="Asia/Singapore">Asia/Singapore (新加坡时间)</option>
                  <option value="America/New_York">America/New_York (美东时间)</option>
                  <option value="America/Los_Angeles">America/Los_Angeles (美西时间)</option>
                  <option value="Europe/London">Europe/London (伦敦时间)</option>
                  <option value="UTC">UTC (协调世界时)</option>
                </select>
                <p className="text-xs text-muted-foreground mt-1">
                  定时抓取使用的时区
                </p>
              </div>
              <div>
                <label className="text-sm font-medium">质量阈值 (1-10)</label>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  step={0.1}
                  value={config.quality_threshold}
                  onChange={(e) => setConfig({ ...config, quality_threshold: parseFloat(e.target.value) || 7.0 })}
                  className="mt-1"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  低于此分数的文章不会自动生成卡片
                </p>
              </div>
              <div>
                <label className="text-sm font-medium">并发处理数</label>
                <Input
                  type="number"
                  min={1}
                  value={config.concurrency ?? 3}
                  onChange={(e) => setConfig({ ...config, concurrency: parseInt(e.target.value) || 3 })}
                  className="mt-1"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  同时处理的文章数量，增大可提高抓取速度。默认 3
                </p>
              </div>
            </div>

            <div className="flex items-center gap-6">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={config.auto_analyze}
                  onChange={(e) => setConfig({ ...config, auto_analyze: e.target.checked })}
                  className="h-4 w-4 rounded border-gray-300"
                />
                自动深度分析
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={config.auto_create_cards}
                  onChange={(e) => setConfig({ ...config, auto_create_cards: e.target.checked })}
                  className="h-4 w-4 rounded border-gray-300"
                />
                自动生成卡片
              </label>
            </div>

            <div className="flex gap-2">
              <Button onClick={handleSave} disabled={saving} size="sm">
                {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
                {saving ? "保存中..." : "保存配置"}
              </Button>
              <Button onClick={handleRun} disabled={running} variant="default" size="sm">
                {running ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-1 h-4 w-4" />
                )}
                {running ? "抓取中..." : "立即抓取"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Manual trigger for non-admin */}
      {!isAdmin && (
        <Card>
          <CardContent className="py-4">
            <p className="text-sm text-muted-foreground">
              仅管理员可以配置和触发抓取。您可以查看抓取日志。
            </p>
          </CardContent>
        </Card>
      )}

      {/* Logs */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <FileText className="h-5 w-5" />
          抓取日志
        </h3>
        {logs.length > 0 && isAdmin && (
          <Button variant="ghost" size="sm" className="text-destructive" onClick={handleClearLogs}>
            <Trash2 className="mr-1 h-4 w-4" />
            清除日志
          </Button>
        )}
      </div>

      {logs.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            暂无抓取日志
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {logs.map((log) => {
            const entries = parseLogEntries(log.log_detail);
            const isExpanded = expandedLog === log.id;
            const isRunning = log.status === "running";
            return (
              <Card key={log.id}>
                <div
                  className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
                  onClick={() => setExpandedLog(isExpanded ? null : log.id)}
                >
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {log.status === "success" ? (
                      <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
                    ) : log.status === "error" ? (
                      <XCircle className="h-5 w-5 text-red-500 shrink-0" />
                    ) : log.status === "cancelled" ? (
                      <Ban className="h-5 w-5 text-amber-500 shrink-0" />
                    ) : (
                      <Loader2 className="h-5 w-5 text-blue-500 animate-spin shrink-0" />
                    )}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">
                          {new Date(log.started_at).toLocaleString("zh-CN", { timeZone: log.timezone || "Asia/Shanghai" })}
                          <span className="text-xs text-muted-foreground ml-1">
                            ({log.timezone || "Asia/Shanghai"})
                          </span>
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {log.run_type === "manual" ? "手动" : "定时"}
                        </Badge>
                        {log.status === "cancelled" && (
                          <Badge variant="secondary" className="text-xs text-amber-600">
                            已取消
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                        <span>来源 {log.sources_processed}</span>
                        <span>发现 {log.articles_fetched}</span>
                        <span>分析 {log.articles_analyzed}</span>
                        <span>跳过 {log.articles_skipped}</span>
                        <span>卡片 {log.cards_created}</span>
                        {log.errors_count > 0 && (
                          <span className={isRunning ? "text-amber-500" : "text-red-500"}>
                            {isRunning ? "⚠️" : "错误"} {log.errors_count}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {/* Cancel button — inline confirm, not modal */}
                    {isRunning && isAdmin && (
                      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                        {confirmCancelId === log.id ? (
                          <>
                            <Button
                              variant="destructive"
                              size="sm"
                              className="h-7 text-xs px-2"
                              disabled={cancelling}
                              onClick={() => handleCancel(log.id)}
                            >
                              {cancelling ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
                              确认取消
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 text-xs px-2"
                              onClick={() => setConfirmCancelId(null)}
                            >
                              返回
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs px-2 text-amber-600 hover:text-amber-700"
                            onClick={() => setConfirmCancelId(log.id)}
                          >
                            <Square className="h-3 w-3 mr-1" />
                            取消抓取
                          </Button>
                        )}
                      </div>
                    )}
                    {isExpanded ? (
                      <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                </div>

                {isExpanded && entries.length > 0 && (
                  <CardContent className="pt-0 pb-3">
                    <div className="border rounded-md bg-muted/30 p-3 max-h-[400px] overflow-y-auto space-y-1">
                      {entries.map((entry, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs">
                          <span className="text-muted-foreground font-mono shrink-0 w-14">
                            {entry.time}
                          </span>
                          {levelIcon(entry.level)}
                          <span className="font-medium shrink-0 min-w-[60px] text-muted-foreground">
                            {entry.source}
                          </span>
                          <span className={cn(
                            "break-all",
                            entry.level === "error" ? "text-red-600 dark:text-red-400" :
                            entry.level === "warn" ? "text-amber-600 dark:text-amber-400" :
                            entry.level === "skip" ? "text-muted-foreground" :
                            "text-foreground"
                          )}>
                            {entry.message}
                          </span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
