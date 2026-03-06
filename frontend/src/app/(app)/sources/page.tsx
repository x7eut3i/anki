"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { sources as sourcesApi } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Trash2,
  FlaskConical,
  Loader2,
  Check,
  X,
  Globe,
  Rss,
  ToggleLeft,
  ToggleRight,
  ExternalLink,
  Calendar,
  FileText,
  AlertCircle,
  RefreshCw,
  CalendarRange,
  BookOpen,
} from "lucide-react";

interface Source {
  id: number;
  name: string;
  url: string;
  source_type: string;
  category: string;
  is_enabled: boolean;
  is_system: boolean;
  description: string;
  last_fetched_at: string | null;
  created_at: string;
}

interface TestResult {
  success: boolean;
  message: string;
  titles: string[];
  first_article?: {
    title: string;
    url: string;
    date: string;
    body_preview: string;
  } | null;
}

export default function SourcesPage() {
  const { token } = useAuthStore();
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [testing, setTesting] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number } & TestResult | null>(null);
  const [resetting, setResetting] = useState(false);
  const [backfillOpen, setBackfillOpen] = useState(false);
  const [backfillLoading, setBackfillLoading] = useState(false);
  const [backfillDates, setBackfillDates] = useState({ start_date: "", end_date: "" });
  const [backfillResult, setBackfillResult] = useState<{ ok: boolean; message: string } | null>(null);

  // 求是 backfill state
  const [qsOpen, setQsOpen] = useState(false);
  const [qsYear, setQsYear] = useState(new Date().getFullYear());
  const [qsIssues, setQsIssues] = useState<{ issue: number; text: string; url: string }[]>([]);
  const [qsLoadingIssues, setQsLoadingIssues] = useState(false);
  const [qsSelectedIssue, setQsSelectedIssue] = useState<{ issue: number; text: string; url: string } | null>(null);
  const [qsBackfillLoading, setQsBackfillLoading] = useState(false);
  const [qsResult, setQsResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Form state
  const [form, setForm] = useState({ name: "", url: "", source_type: "rss", category: "时政热点", description: "" });

  const fetchSources = async () => {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    try {
      const data = await sourcesApi.list(token);
      setSources(data);
    } catch (err: any) {
      console.error("Failed to load sources:", err);
      setLoadError(err.message || "加载来源列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSources(); }, [token]);

  const handleAdd = async () => {
    if (!token || !form.name.trim() || !form.url.trim()) return;
    try {
      await sourcesApi.create(form, token);
      setShowAdd(false);
      setForm({ name: "", url: "", source_type: "rss", category: "时政热点", description: "" });
      fetchSources();
    } catch (err: any) {
      alert("添加失败: " + (err.message || "未知错误"));
    }
  };

  const handleUpdate = async (id: number) => {
    if (!token) return;
    try {
      await sourcesApi.update(id, form, token);
      setEditingId(null);
      setTestResult(null);
      fetchSources();
    } catch (err: any) {
      alert("更新失败: " + (err.message || "未知错误"));
    }
  };

  const handleDelete = async (id: number) => {
    if (!token || !confirm("确认删除此来源？")) return;
    try {
      await sourcesApi.delete(id, token);
      if (editingId === id) { setEditingId(null); setTestResult(null); }
      fetchSources();
    } catch (err: any) {
      alert("删除失败: " + (err.message || "未知错误"));
    }
  };

  const handleTest = async (id: number) => {
    if (!token) return;
    setTesting(id);
    setTestResult(null);
    try {
      const result = await sourcesApi.test(id, token);
      setTestResult({
        id,
        success: result.success,
        message: result.message,
        titles: result.sample_titles || [],
        first_article: result.first_article || null,
      });
    } catch (err: any) {
      setTestResult({ id, success: false, message: err.message || "测试失败", titles: [], first_article: null });
    } finally {
      setTesting(null);
    }
  };

  const startEdit = (source: Source) => {
    setEditingId(source.id);
    setTestResult(null);
    setForm({
      name: source.name,
      url: source.url,
      source_type: source.source_type,
      category: source.category,
      description: source.description,
    });
  };

  const handleToggle = async (source: Source) => {
    if (!token) return;
    try {
      await sourcesApi.update(source.id, { is_enabled: !source.is_enabled }, token);
      fetchSources();
    } catch (err) {
      console.error("Toggle failed:", err);
    }
  };

  const handleResetDefaults = async () => {
    if (!token || !confirm("确认恢复默认来源？\n这将删除当前所有来源，替换为 2 个系统来源 + 19 个普通来源。")) return;
    setResetting(true);
    try {
      const result = await sourcesApi.resetDefaults(token);
      setSources(result.sources || []);
      setEditingId(null);
      setTestResult(null);
    } catch (err: any) {
      alert("恢复失败: " + (err.message || "未知错误"));
    } finally {
      setResetting(false);
    }
  };

  const handleBackfill = async () => {
    if (!token || !backfillDates.start_date || !backfillDates.end_date) return;
    setBackfillLoading(true);
    setBackfillResult(null);
    try {
      const result = await sourcesApi.backfill(backfillDates, token);
      setBackfillResult({ ok: true, message: result.message });
    } catch (err: any) {
      setBackfillResult({ ok: false, message: err.message || "回溯抓取启动失败" });
    } finally {
      setBackfillLoading(false);
    }
  };

  const handleQsLoadIssues = async (year: number) => {
    if (!token) return;
    setQsLoadingIssues(true);
    setQsIssues([]);
    setQsSelectedIssue(null);
    setQsResult(null);
    try {
      const result = await sourcesApi.qiushiIssues(year, token);
      setQsIssues(result.issues || []);
    } catch (err: any) {
      setQsResult({ ok: false, message: "获取期刊列表失败: " + (err.message || "未知错误") });
    } finally {
      setQsLoadingIssues(false);
    }
  };

  const handleQsBackfill = async () => {
    if (!token || !qsSelectedIssue) return;
    setQsBackfillLoading(true);
    setQsResult(null);
    try {
      const result = await sourcesApi.qiushiBackfill(
        { issue_url: qsSelectedIssue.url, issue_name: `${qsYear}年 ${qsSelectedIssue.text}` },
        token,
      );
      setQsResult({ ok: true, message: result.message });
    } catch (err: any) {
      setQsResult({ ok: false, message: err.message || "回溯抓取启动失败" });
    } finally {
      setQsBackfillLoading(false);
    }
  };

  /** Render the test result panel */
  const renderTestResult = (sourceId: number) => {
    if (!testResult || testResult.id !== sourceId) return null;
    const r = testResult;
    return (
      <div className={`p-4 rounded-lg text-sm space-y-3 ${r.success ? "bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800" : "bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800"}`}>
        <p className={`font-medium ${r.success ? "text-green-700 dark:text-green-300" : "text-red-700 dark:text-red-300"}`}>
          {r.success ? "✅" : "❌"} {r.message}
        </p>
        {r.titles.length > 0 && (
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1">文章列表（前5篇）：</p>
            {r.titles.map((t, i) => (
              <p key={i} className="text-xs text-muted-foreground">• {t}</p>
            ))}
          </div>
        )}
        {r.first_article && (
          <div className="border-t pt-3 space-y-2">
            <p className="text-xs font-semibold text-foreground flex items-center gap-1">
              <FileText className="h-3 w-3" /> 第一篇文章解析结果：
            </p>
            <div className="bg-background rounded-md p-3 space-y-2 border">
              <div>
                <span className="text-xs font-medium text-muted-foreground">标题：</span>
                <span className="text-sm font-medium">{r.first_article.title}</span>
              </div>
              {r.first_article.date && (
                <div className="flex items-center gap-1">
                  <Calendar className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">日期：</span>
                  <span className="text-xs">{r.first_article.date}</span>
                </div>
              )}
              {r.first_article.url && (
                <div className="flex items-center gap-1 min-w-0">
                  <ExternalLink className="h-3 w-3 text-muted-foreground shrink-0" />
                  <a
                    href={r.first_article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 dark:text-blue-400 truncate hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {r.first_article.url}
                  </a>
                </div>
              )}
              {r.first_article.body_preview && (
                <div>
                  <span className="text-xs font-medium text-muted-foreground">正文预览：</span>
                  <div className="mt-1 text-xs text-muted-foreground bg-muted/50 rounded p-2 max-h-[200px] overflow-y-auto whitespace-pre-line leading-relaxed">
                    {r.first_article.body_preview}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        {r.success && !r.first_article && (
          <div className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
            <AlertCircle className="h-3 w-3" />
            未能获取第一篇文章的详细内容
          </div>
        )}
      </div>
    );
  };

  /** Render edit form (used in both add-new and edit-existing) */
  const renderEditForm = (sourceId: number | null, onSave: () => void, onCancel: () => void) => (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-muted-foreground">名称 <span className="text-red-500">*</span></label>
          <Input placeholder="如：人民日报-时政" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1" />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground">类型</label>
          <select
            value={form.source_type}
            onChange={(e) => setForm({ ...form, source_type: e.target.value })}
            className="w-full h-9 mt-1 px-3 rounded-md border border-input bg-background text-sm"
          >
            <option value="rss">RSS</option>
            <option value="html">网页</option>
          </select>
        </div>
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground">URL <span className="text-red-500">*</span></label>
        <Input placeholder="https://..." value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} className="mt-1" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-muted-foreground">分类</label>
          <Input placeholder="时政热点" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="mt-1" />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground">描述</label>
          <Input placeholder="可选描述" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="mt-1" />
        </div>
      </div>

      {/* Test result inside edit form */}
      {sourceId && renderTestResult(sourceId)}

      <div className="flex gap-2">
        <Button size="sm" onClick={onSave} disabled={!form.name.trim() || !form.url.trim()}>
          <Check className="mr-1 h-4 w-4" /> 保存
        </Button>
        {sourceId && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleTest(sourceId)}
            disabled={testing === sourceId}
            title="测试连接并解析第一篇文章"
          >
            {testing === sourceId ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <FlaskConical className="mr-1 h-4 w-4" />
            )}
            测试抓取
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onCancel}>
          <X className="mr-1 h-4 w-4" /> 取消
        </Button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">来源管理</h2>
          <p className="text-muted-foreground">管理文章抓取来源，支持 RSS 和网页解析</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleResetDefaults}
            disabled={resetting}
            title="删除当前所有来源，恢复为系统预设的优质来源"
          >
            {resetting ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-1 h-4 w-4" />
            )}
            恢复默认
          </Button>
          <Button onClick={() => { setShowAdd(!showAdd); setEditingId(null); setTestResult(null); }}>
            <Plus className="mr-1 h-4 w-4" />
            添加来源
          </Button>
        </div>
      </div>

      {/* Add form */}
      {showAdd && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">➕ 添加新来源</CardTitle>
          </CardHeader>
          <CardContent>
            {renderEditForm(null, handleAdd, () => setShowAdd(false))}
          </CardContent>
        </Card>
      )}

      {/* Source list */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : loadError ? (
        <Card>
          <CardContent className="py-8 text-center space-y-3">
            <div className="flex items-center justify-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              <span className="font-medium">加载失败</span>
            </div>
            <p className="text-sm text-muted-foreground">{loadError}</p>
            <Button variant="outline" size="sm" onClick={fetchSources}>
              <RefreshCw className="h-4 w-4 mr-1" />
              重试
            </Button>
          </CardContent>
        </Card>
      ) : sources.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            暂无来源，点击"添加来源"创建
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {sources.map((source) => (
            <Card key={source.id} className={!source.is_enabled ? "opacity-60" : ""}>
              {editingId === source.id ? (
                <CardContent className="pt-4">
                  {renderEditForm(source.id, () => handleUpdate(source.id), () => { setEditingId(null); setTestResult(null); })}
                </CardContent>
              ) : (
                <CardContent
                  className={`pt-4 ${!source.is_system ? "cursor-pointer hover:bg-muted/50 transition-colors rounded-lg" : ""}`}
                  onClick={() => { if (!source.is_system) startEdit(source); }}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {source.source_type === "rss" ? (
                          <Rss className="h-4 w-4 text-orange-500 shrink-0" />
                        ) : source.is_system ? (
                          <Globe className="h-4 w-4 text-indigo-500 shrink-0" />
                        ) : (
                          <Globe className="h-4 w-4 text-blue-500 shrink-0" />
                        )}
                        <span className="font-medium">{source.name}</span>
                        <Badge variant="outline" className="text-xs">{source.category}</Badge>
                        {source.is_system && <Badge className="text-xs bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300 border-indigo-200 dark:border-indigo-700">系统</Badge>}
                        {!source.is_enabled && <Badge variant="secondary" className="text-xs">已禁用</Badge>}
                      </div>
                      <p className="text-xs text-muted-foreground truncate">{source.url}</p>
                      {source.is_system && (
                        <p className="text-xs text-indigo-600 dark:text-indigo-400 mt-1">系统来源使用特殊抓取规则，不可编辑或删除</p>
                      )}
                      {source.is_system && source.name.includes("人民日报") && (
                        <div className="mt-2">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={(e) => {
                              e.stopPropagation();
                              setBackfillOpen(!backfillOpen);
                              setBackfillResult(null);
                              if (!backfillDates.start_date) {
                                const today = new Date();
                                const weekAgo = new Date(today);
                                weekAgo.setDate(weekAgo.getDate() - 7);
                                setBackfillDates({
                                  start_date: weekAgo.toISOString().split("T")[0],
                                  end_date: today.toISOString().split("T")[0],
                                });
                              }
                            }}
                          >
                            <CalendarRange className="h-3.5 w-3.5" />
                            回溯抓取
                          </Button>
                          {backfillOpen && (
                            <div
                              className="mt-2 p-3 rounded-lg border bg-muted/30 space-y-3"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <p className="text-xs text-muted-foreground">
                                选择日期范围，抓取该时段内的人民日报文章（最多60天）。抓取任务会在后台运行，可在「自动抓取」页面查看进度。
                              </p>
                              <div className="flex items-center gap-2 flex-wrap">
                                <div className="flex items-center gap-1.5">
                                  <label className="text-xs font-medium text-muted-foreground whitespace-nowrap">起始</label>
                                  <input
                                    type="date"
                                    value={backfillDates.start_date}
                                    onChange={(e) => setBackfillDates({ ...backfillDates, start_date: e.target.value })}
                                    className="h-8 px-2 rounded-md border border-input bg-background text-xs"
                                  />
                                </div>
                                <div className="flex items-center gap-1.5">
                                  <label className="text-xs font-medium text-muted-foreground whitespace-nowrap">截止</label>
                                  <input
                                    type="date"
                                    value={backfillDates.end_date}
                                    onChange={(e) => setBackfillDates({ ...backfillDates, end_date: e.target.value })}
                                    className="h-8 px-2 rounded-md border border-input bg-background text-xs"
                                  />
                                </div>
                                <Button
                                  size="sm"
                                  className="h-8 text-xs gap-1"
                                  disabled={backfillLoading || !backfillDates.start_date || !backfillDates.end_date}
                                  onClick={handleBackfill}
                                >
                                  {backfillLoading ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <Check className="h-3.5 w-3.5" />
                                  )}
                                  开始回溯
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-8 text-xs"
                                  onClick={() => { setBackfillOpen(false); setBackfillResult(null); }}
                                >
                                  取消
                                </Button>
                              </div>
                              {backfillDates.start_date && backfillDates.end_date && (() => {
                                const days = Math.floor((new Date(backfillDates.end_date).getTime() - new Date(backfillDates.start_date).getTime()) / 86400000) + 1;
                                return days > 0 ? (
                                  <p className="text-xs text-muted-foreground">
                                    共 <span className="font-medium text-foreground">{days}</span> 天
                                    {days > 60 && <span className="text-red-500 ml-1">（超过60天上限，将自动截断）</span>}
                                  </p>
                                ) : null;
                              })()}
                              {backfillResult && (
                                <div className={`text-xs p-2 rounded ${backfillResult.ok ? "bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300" : "bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300"}`}>
                                  {backfillResult.ok ? "✅" : "❌"} {backfillResult.message}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                      {source.is_system && source.name.includes("求是") && (
                        <div className="mt-2">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={(e) => {
                              e.stopPropagation();
                              setQsOpen(!qsOpen);
                              setQsResult(null);
                            }}
                          >
                            <BookOpen className="h-3.5 w-3.5" />
                            回溯抓取
                          </Button>
                          {qsOpen && (
                            <div
                              className="mt-2 p-3 rounded-lg border bg-muted/30 space-y-3"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <p className="text-xs text-muted-foreground">
                                选择年份查询期刊列表，再选择一期进行回溯抓取。抓取任务会在后台运行，可在「自动抓取」页面查看进度。
                              </p>
                              {/* Step 1: Year selector */}
                              <div className="flex items-center gap-2 flex-wrap">
                                <div className="flex items-center gap-1.5">
                                  <label className="text-xs font-medium text-muted-foreground whitespace-nowrap">年份</label>
                                  <select
                                    value={qsYear}
                                    onChange={(e) => {
                                      setQsYear(Number(e.target.value));
                                      setQsIssues([]);
                                      setQsSelectedIssue(null);
                                      setQsResult(null);
                                    }}
                                    className="h-8 px-2 rounded-md border border-input bg-background text-xs"
                                  >
                                    {Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - i).map((y) => (
                                      <option key={y} value={y}>{y}年</option>
                                    ))}
                                  </select>
                                </div>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-8 text-xs gap-1"
                                  disabled={qsLoadingIssues}
                                  onClick={() => handleQsLoadIssues(qsYear)}
                                >
                                  {qsLoadingIssues ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <FileText className="h-3.5 w-3.5" />
                                  )}
                                  查询期刊
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="h-8 text-xs"
                                  onClick={() => { setQsOpen(false); setQsResult(null); setQsIssues([]); setQsSelectedIssue(null); }}
                                >
                                  取消
                                </Button>
                              </div>
                              {/* Step 2: Issue selector */}
                              {qsIssues.length > 0 && (
                                <div className="space-y-2">
                                  <p className="text-xs font-medium text-muted-foreground">
                                    {qsYear}年 共 {qsIssues.length} 期，选择一期：
                                  </p>
                                  <div className="flex flex-wrap gap-1.5">
                                    {qsIssues.map((iss) => (
                                      <Button
                                        key={iss.issue}
                                        size="sm"
                                        variant={qsSelectedIssue?.issue === iss.issue ? "default" : "outline"}
                                        className="h-7 text-xs px-2.5"
                                        onClick={() => { setQsSelectedIssue(iss); setQsResult(null); }}
                                      >
                                        {iss.text}
                                      </Button>
                                    ))}
                                  </div>
                                  {qsSelectedIssue && (
                                    <div className="flex items-center gap-2 pt-1">
                                      <span className="text-xs text-muted-foreground">
                                        已选: <span className="font-medium text-foreground">{qsSelectedIssue.text}</span>
                                      </span>
                                      <Button
                                        size="sm"
                                        className="h-8 text-xs gap-1"
                                        disabled={qsBackfillLoading}
                                        onClick={handleQsBackfill}
                                      >
                                        {qsBackfillLoading ? (
                                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                        ) : (
                                          <Check className="h-3.5 w-3.5" />
                                        )}
                                        开始抓取
                                      </Button>
                                    </div>
                                  )}
                                </div>
                              )}
                              {qsLoadingIssues && qsIssues.length === 0 && (
                                <p className="text-xs text-muted-foreground flex items-center gap-1">
                                  <Loader2 className="h-3 w-3 animate-spin" /> 正在查询期刊列表...
                                </p>
                              )}
                              {qsResult && (
                                <div className={`text-xs p-2 rounded ${qsResult.ok ? "bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300" : "bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300"}`}>
                                  {qsResult.ok ? "✅" : "❌"} {qsResult.message}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                      {!source.is_system && (
                        <p className="text-xs text-muted-foreground/60 mt-1">点击编辑</p>
                      )}
                      {source.description && (
                        <p className="text-xs text-muted-foreground mt-1">{source.description}</p>
                      )}
                      {source.last_fetched_at && (
                        <p className="text-[10px] text-muted-foreground mt-1">
                          上次测试: {formatDateTime(source.last_fetched_at)}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        title="测试抓取"
                        onClick={() => handleTest(source.id)}
                        disabled={testing === source.id}
                      >
                        {testing === source.id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <FlaskConical className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        title={source.is_enabled ? "点击禁用此来源" : "点击启用此来源"}
                        onClick={() => handleToggle(source)}
                      >
                        {source.is_enabled ? (
                          <ToggleRight className="h-4 w-4 text-green-600" />
                        ) : (
                          <ToggleLeft className="h-4 w-4 text-muted-foreground" />
                        )}
                      </Button>
                      {!source.is_system && (
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" title="删除来源" onClick={() => handleDelete(source.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                  {/* Test result for non-editing cards */}
                  {renderTestResult(source.id)}
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
