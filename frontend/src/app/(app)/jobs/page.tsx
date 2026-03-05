"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "@/lib/store";
import { jobs as jobsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Loader2,
  Trash2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Play,
  AlertTriangle,
} from "lucide-react";

interface AIJob {
  id: number;
  job_type: string;
  title: string;
  status: string;
  progress: number;
  result_json: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  pending: { label: "等待中", color: "bg-yellow-100 text-yellow-800", icon: Clock },
  running: { label: "运行中", color: "bg-blue-100 text-blue-800", icon: Play },
  completed: { label: "已完成", color: "bg-green-100 text-green-800", icon: CheckCircle2 },
  failed: { label: "失败", color: "bg-red-100 text-red-800", icon: XCircle },
};

export default function JobsPage() {
  const { token } = useAuthStore();
  const [jobsList, setJobsList] = useState<AIJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadJobs = useCallback(async () => {
    if (!token) return;
    try {
      const data = await jobsApi.list(token, statusFilter || undefined);
      setJobsList(data || []);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Auto-refresh every 5 seconds if there are pending/running jobs
  useEffect(() => {
    if (!autoRefresh) return;
    const hasActive = jobsList.some((j) => j.status === "pending" || j.status === "running");
    if (!hasActive) return;
    const timer = setInterval(loadJobs, 5000);
    return () => clearInterval(timer);
  }, [autoRefresh, jobsList, loadJobs]);

  const handleDelete = async (jobId: number) => {
    if (!token || !confirm("确定删除此任务记录？")) return;
    try {
      await jobsApi.delete(jobId, token);
      setJobsList((prev) => prev.filter((j) => j.id !== jobId));
    } catch (err: any) {
      alert(err.message || "删除失败");
    }
  };

  const handleClearCompleted = async () => {
    if (!token || !confirm("确定清除所有已完成/已失败的任务？")) return;
    try {
      await jobsApi.clearCompleted(token);
      loadJobs();
    } catch (err: any) {
      alert(err.message || "清除失败");
    }
  };

  const parseResult = (resultJson: string | null): Record<string, any> | null => {
    if (!resultJson) return null;
    try {
      return JSON.parse(resultJson);
    } catch {
      return null;
    }
  };

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return "—";
    return new Date(dateStr).toLocaleString("zh-CN");
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">AI 任务</h2>
          <p className="text-muted-foreground">
            查看异步AI任务的执行状态和结果
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadJobs}
            disabled={loading}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            刷新
          </Button>
          {jobsList.some((j) => j.status === "completed" || j.status === "failed") && (
            <Button
              variant="outline"
              size="sm"
              className="text-destructive"
              onClick={handleClearCompleted}
            >
              <Trash2 className="h-4 w-4 mr-1" />
              清除已完成
            </Button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2">
        {["", "pending", "running", "completed", "failed"].map((s) => (
          <Button
            key={s}
            size="sm"
            variant={statusFilter === s ? "default" : "outline"}
            onClick={() => setStatusFilter(s)}
          >
            {s === "" ? "全部" : STATUS_CONFIG[s]?.label || s}
          </Button>
        ))}
        <label className="flex items-center gap-1.5 text-xs ml-4 cursor-pointer select-none">
          <input
            type="checkbox"
            className="rounded"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          自动刷新
        </label>
      </div>

      {jobsList.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <Clock className="h-12 w-12 text-muted-foreground opacity-30" />
            <p className="text-muted-foreground">暂无AI任务</p>
            <p className="text-xs text-muted-foreground">
              通过智能导入或批量丰富功能发起异步任务
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {jobsList.map((job) => {
            const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
            const Icon = cfg.icon;
            const result = parseResult(job.result_json);

            return (
              <Card key={job.id}>
                <CardContent className="py-4">
                  <div className="flex items-start gap-3">
                    <div className={`rounded-full p-2 ${cfg.color}`}>
                      {job.status === "running" ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Icon className="h-4 w-4" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">
                          {job.title || job.job_type}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {{
                            smart_import: "智能导入",
                            batch_enrich: "批量丰富",
                            add_article: "文章分析",
                            reanalyze: "重新分析",
                            complete_cards: "AI生成卡片",
                            import_cards: "导入卡片",
                          }[job.job_type] || job.job_type}
                        </Badge>
                        <Badge className={`text-xs ${cfg.color}`}>
                          {cfg.label}
                        </Badge>
                      </div>

                      {/* Progress bar for running jobs */}
                      {(job.status === "running" || job.status === "pending") && (
                        <div className="mt-2">
                          <Progress value={job.progress} className="h-1.5" />
                          <span className="text-xs text-muted-foreground mt-0.5 block">
                            {job.progress}%
                          </span>
                        </div>
                      )}

                      {/* Result summary */}
                      {result && job.status === "completed" && (
                        <div className="mt-2 text-xs text-muted-foreground bg-muted/50 rounded-md p-2">
                          {result.message || result.detail || (
                            <>
                              {result.imported != null && <span>导入: {result.imported} </span>}
                              {result.enriched != null && <span>丰富: {result.enriched} </span>}
                              {result.cards_created != null && <span>生成卡片: {result.cards_created} </span>}
                              {result.quality_score != null && <span>质量评分: {result.quality_score} </span>}
                              {result.skipped != null && <span>跳过: {result.skipped} </span>}
                              {result.errors != null && <span>错误: {result.errors} </span>}
                            </>
                          )}
                        </div>
                      )}

                      {/* Error message */}
                      {job.error_message && job.status === "failed" && (
                        <div className="mt-2 text-xs text-red-600 bg-red-50 dark:bg-red-950/30 rounded-md p-2 flex items-start gap-1">
                          <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                          <span>{job.error_message}</span>
                        </div>
                      )}

                      {/* Timestamps */}
                      <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                        <span>创建: {formatTime(job.created_at)}</span>
                        {job.started_at && <span>开始: {formatTime(job.started_at)}</span>}
                        {job.completed_at && <span>完成: {formatTime(job.completed_at)}</span>}
                      </div>
                    </div>

                    {/* Delete button (only for completed/failed) */}
                    {(job.status === "completed" || job.status === "failed") && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive shrink-0"
                        onClick={() => handleDelete(job.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
