"use client";

import React, { useState, useEffect } from "react";
import { useAuthStore } from "@/lib/store";
import { getUserTimezone } from "@/lib/timezone";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  BarChart3, RefreshCw, Zap, Clock, AlertCircle, Hash,
  Bot, Activity, Globe, FileText, TrendingUp,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function fetchStats(endpoint: string, token: string, days: number) {
  const tz = getUserTimezone();
  const res = await fetch(`${API_BASE}/api/stats/${endpoint}?days=${days}&tz=${encodeURIComponent(tz)}`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`Failed to fetch ${endpoint} stats`);
  return res.json();
}

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: any; label: string; value: string | number; sub?: string; color?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className={`text-2xl font-bold ${color || ""}`}>{value}</p>
            {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
          </div>
          <Icon className={`h-8 w-8 ${color || "text-muted-foreground"} opacity-50`} />
        </div>
      </CardContent>
    </Card>
  );
}

function DailyChart({ data, label = "调用" }: { data: any[]; label?: string }) {
  if (!data || data.length === 0) return <p className="text-muted-foreground text-sm">暂无数据</p>;
  const maxCount = Math.max(...data.map((d) => d.count || 0), 1);
  const recent = data.slice(-30);
  return (
    <div>
      <div className="flex items-end gap-[2px] h-32">
        {recent.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-center gap-1 group relative">
            <div
              className={`w-full rounded-t ${d.errors > 0 ? "bg-red-400" : "bg-primary"} transition-all`}
              style={{ height: `${Math.max((d.count / maxCount) * 128, d.count > 0 ? 4 : 0)}px` }}
            />
            <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-popover border rounded px-2 py-1 text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none shadow-lg z-10">
              {d.date}: {d.count}{label} · {(d.tokens || 0).toLocaleString()} tokens
              {d.errors > 0 && ` · ${d.errors}错误`}
            </div>
          </div>
        ))}
      </div>
      {recent.length > 0 && (
        <div className="flex justify-between text-xs text-muted-foreground mt-2">
          <span>{recent[0]?.date}</span>
          <span>{recent[recent.length - 1]?.date}</span>
        </div>
      )}
    </div>
  );
}

function ContentChart({ data }: { data: any[] }) {
  if (!data || data.length === 0) return <p className="text-muted-foreground text-sm">暂无数据</p>;
  const maxVal = Math.max(...data.map((d) => Math.max(d.articles || 0, d.cards || 0)), 1);
  const recent = data.slice(-30);
  return (
    <div>
      <div className="flex items-end gap-[2px] h-32">
        {recent.map((d, i) => (
          <div key={i} className="flex-1 flex flex-col items-end gap-0 group relative">
            <div className="w-full flex flex-col items-stretch gap-[1px]">
              <div
                className="w-full bg-blue-500 rounded-t"
                style={{ height: `${Math.max((d.articles / maxVal) * 60, d.articles > 0 ? 3 : 0)}px` }}
              />
              <div
                className="w-full bg-green-500"
                style={{ height: `${Math.max((d.cards / maxVal) * 60, d.cards > 0 ? 3 : 0)}px` }}
              />
            </div>
            <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-popover border rounded px-2 py-1 text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none shadow-lg z-10">
              {d.date}: {d.articles}篇文章 · {d.cards}张卡片
            </div>
          </div>
        ))}
      </div>
      {recent.length > 0 && (
        <div className="flex justify-between text-xs text-muted-foreground mt-2">
          <span>{recent[0]?.date}</span>
          <span>{recent[recent.length - 1]?.date}</span>
        </div>
      )}
      <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-blue-500" /> 文章</span>
        <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-green-500" /> 卡片</span>
      </div>
    </div>
  );
}

export default function AIStatsPage() {
  const { token } = useAuthStore();
  const [aiStats, setAiStats] = useState<any>(null);
  const [contentStats, setContentStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);

  const fetchAll = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [ai, content] = await Promise.all([
        fetchStats("ai", token, days),
        fetchStats("content", token, days),
      ]);
      setAiStats(ai);
      setContentStats(content);
    } catch (e) {
      console.error("Failed to fetch stats:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, [token, days]);

  if (!aiStats) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 className="h-6 w-6" /> AI 统计
        </h1>
        <div className="flex items-center gap-2">
          <select
            className="border rounded-md px-2 py-1 text-sm bg-background"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>最近7天</option>
            <option value={30}>最近30天</option>
            <option value={90}>最近90天</option>
            <option value={365}>最近一年</option>
          </select>
          <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* AI Overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard icon={Zap} label="AI调用" value={aiStats.total_calls} color="text-primary" />
        <StatCard
          icon={AlertCircle} label="错误"
          value={aiStats.total_errors}
          sub={aiStats.total_calls > 0 ? `错误率 ${((aiStats.total_errors / aiStats.total_calls) * 100).toFixed(1)}%` : undefined}
          color={aiStats.total_errors > 0 ? "text-red-500" : "text-green-500"}
        />
        <StatCard icon={Hash} label="Token用量" value={aiStats.total_tokens.toLocaleString()} color="text-blue-500" />
        <StatCard
          icon={Clock} label="平均延迟"
          value={`${(aiStats.avg_latency_ms / 1000).toFixed(1)}s`}
          sub={`最长 ${(aiStats.max_latency_ms / 1000).toFixed(1)}s`}
          color="text-orange-500"
        />
      </div>

      {/* AI Daily Trend */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="h-4 w-4" /> AI 每日调用趋势
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DailyChart data={aiStats.daily} label="次" />
        </CardContent>
      </Card>

      {/* Content Stats */}
      {contentStats && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard icon={FileText} label="文章分析" value={contentStats.total_articles} color="text-indigo-500" />
            <StatCard icon={Bot} label="AI生成卡片" value={contentStats.total_ai_cards} color="text-emerald-500" />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <TrendingUp className="h-4 w-4" /> 文章 & 卡片每日趋势
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ContentChart data={contentStats.daily} />
            </CardContent>
          </Card>

          {contentStats.by_source && contentStats.by_source.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Globe className="h-4 w-4" /> 按来源统计
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-muted-foreground border-b">
                        <th className="text-left py-2">来源</th>
                        <th className="text-right py-2">文章数</th>
                        <th className="text-right py-2">平均质量</th>
                      </tr>
                    </thead>
                    <tbody>
                      {contentStats.by_source.map((s: any, i: number) => (
                        <tr key={i} className="border-b hover:bg-muted/50">
                          <td className="py-2">{s.source}</td>
                          <td className="text-right">{s.articles}</td>
                          <td className="text-right">{s.avg_quality}/10</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      <div className="grid md:grid-cols-2 gap-6">
        {/* By Feature */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Bot className="h-4 w-4" /> 按功能模块
            </CardTitle>
          </CardHeader>
          <CardContent>
            {aiStats.by_feature && aiStats.by_feature.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted-foreground border-b">
                      <th className="text-left py-1">功能</th>
                      <th className="text-right py-1">调用</th>
                      <th className="text-right py-1">Tokens</th>
                      <th className="text-right py-1">延迟</th>
                      <th className="text-right py-1">错误</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aiStats.by_feature.map((f: any, i: number) => (
                      <tr key={i} className="border-b hover:bg-muted/50">
                        <td className="py-1 font-mono">{f.feature}</td>
                        <td className="text-right">{f.count}</td>
                        <td className="text-right">{f.total_tokens.toLocaleString()}</td>
                        <td className="text-right">{(f.avg_ms / 1000).toFixed(1)}s</td>
                        <td className={`text-right ${f.errors > 0 ? "text-red-500" : ""}`}>{f.errors}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">暂无数据</p>
            )}
          </CardContent>
        </Card>

        {/* By Model + Config */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Zap className="h-4 w-4" /> 按模型 / 配置
            </CardTitle>
          </CardHeader>
          <CardContent>
            {aiStats.by_model && aiStats.by_model.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted-foreground border-b">
                      <th className="text-left py-1">模型</th>
                      <th className="text-left py-1">配置</th>
                      <th className="text-right py-1">调用</th>
                      <th className="text-right py-1">Tokens</th>
                      <th className="text-right py-1">延迟</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aiStats.by_model.map((m: any, i: number) => (
                      <tr key={i} className="border-b hover:bg-muted/50">
                        <td className="py-1 font-mono">{m.model}</td>
                        <td className="py-1 text-muted-foreground">{m.config_name || "-"}</td>
                        <td className="text-right">{m.count}</td>
                        <td className="text-right">{m.total_tokens.toLocaleString()}</td>
                        <td className="text-right">{(m.avg_ms / 1000).toFixed(1)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground text-sm">暂无数据</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Ingestion Runs */}
      {contentStats?.recent_runs && contentStats.recent_runs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <FileText className="h-4 w-4" /> 最近抓取记录
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted-foreground border-b">
                    <th className="text-left py-1">时间</th>
                    <th className="text-right py-1">状态</th>
                    <th className="text-right py-1">抓取</th>
                    <th className="text-right py-1">分析</th>
                    <th className="text-right py-1">制卡</th>
                    <th className="text-right py-1">错误</th>
                  </tr>
                </thead>
                <tbody>
                  {contentStats.recent_runs.map((r: any, i: number) => (
                    <tr key={i} className="border-b hover:bg-muted/50">
                      <td className="py-1 font-mono">{r.date}</td>
                      <td className={`text-right ${r.status === "success" ? "text-green-500" : "text-red-500"}`}>{r.status === "success" ? "成功" : "失败"}</td>
                      <td className="text-right">{r.articles_fetched}</td>
                      <td className="text-right">{r.articles_analyzed}</td>
                      <td className="text-right">{r.cards_created}</td>
                      <td className={`text-right ${r.errors > 0 ? "text-red-500" : ""}`}>{r.errors}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
