"use client";

import React, { useState, useEffect } from "react";
import { useAuthStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  BarChart3, RefreshCw, BookOpen, Clock, TrendingUp, Award,
  Calendar, Brain, Target, Zap, ChevronDown, HelpCircle,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

async function fetchStudyStats(token: string, params: { days?: number; period?: string; start?: string; end?: string }) {
  const q = new URLSearchParams();
  if (params.days) q.set("days", String(params.days));
  if (params.period) q.set("period", params.period);
  if (params.start) q.set("start", params.start);
  if (params.end) q.set("end", params.end);
  const res = await fetch(`${API_BASE}/api/stats/study?${q.toString()}`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to fetch study stats");
  return res.json();
}

function StatCard({ icon: Icon, label, value, sub, color, tooltip }: {
  icon: any; label: string; value: string | number; sub?: string; color?: string; tooltip?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              {label}
              {tooltip && (
                <span className="relative group">
                  <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                  <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 w-52 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                    {tooltip}
                  </span>
                </span>
              )}
            </p>
            <p className={`text-2xl font-bold ${color || ""}`}>{value}</p>
            {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
          </div>
          <Icon className={`h-8 w-8 ${color || "text-muted-foreground"} opacity-50`} />
        </div>
      </CardContent>
    </Card>
  );
}

function DailyReviewChart({ data }: { data: any[] }) {
  if (!data || data.length === 0) return <p className="text-muted-foreground text-sm">暂无数据</p>;
  const maxCount = Math.max(...data.map((d) => d.count || 0), 1);
  const recent = data.slice(-30);

  return (
    <div>
      <div className="flex items-end gap-[2px] h-32">
        {recent.map((d, i) => {
          const height = Math.max((d.count / maxCount) * 128, d.count > 0 ? 4 : 0);
          const againPct = d.count > 0 ? (d.again / d.count) * 100 : 0;
          return (
            <div key={i} className="flex-1 flex flex-col items-center group relative">
              <div className="w-full rounded-t overflow-hidden" style={{ height: `${height}px` }}>
                <div
                  className="w-full bg-green-500"
                  style={{ height: `${100 - againPct}%` }}
                />
                <div
                  className="w-full bg-red-400"
                  style={{ height: `${againPct}%` }}
                />
              </div>
              <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-popover border rounded px-2 py-1 text-xs whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none shadow-lg z-10">
                {d.date}: {d.count}次复习 · {d.new_cards || 0}新卡
                <br />
                保留率: {(d.retention * 100).toFixed(0)}% · {Math.round((d.time_ms || 0) / 60000)}分钟
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between text-xs text-muted-foreground mt-2">
        <span>{recent[0]?.date}</span>
        <span>{recent[recent.length - 1]?.date}</span>
      </div>
      <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-green-500" /> 记住</span>
        <span className="flex items-center gap-1"><div className="w-3 h-3 rounded bg-red-400" /> 忘记</span>
      </div>
    </div>
  );
}

function AggregatedTable({ data, period }: { data: any[]; period: string }) {
  if (!data || data.length === 0) return <p className="text-muted-foreground text-sm">暂无数据</p>;
  const periodLabel = period === "week" ? "周" : period === "month" ? "月" : "日";
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground border-b">
            <th className="text-left py-2 px-1">{periodLabel}</th>
            <th className="text-right py-2 px-1">复习</th>
            <th className="text-right py-2 px-1">新卡</th>
            <th className="text-right py-2 px-1">保留率</th>
            <th className="text-right py-2 px-1">时间</th>
            <th className="text-right py-2 px-1">天数</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-b hover:bg-muted/50">
              <td className="py-2 px-1 font-mono">{row.period || row.date}</td>
              <td className="text-right py-2 px-1">{row.count}</td>
              <td className="text-right py-2 px-1">{row.new_cards}</td>
              <td className={`text-right py-2 px-1 ${row.retention >= 0.9 ? "text-green-500" : row.retention >= 0.7 ? "text-yellow-500" : "text-red-500"}`}>
                {(row.retention * 100).toFixed(1)}%
              </td>
              <td className="text-right py-2 px-1">{Math.round((row.time_ms || 0) / 60000)}分</td>
              <td className="text-right py-2 px-1">{row.days_studied ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RatingBar({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-10 text-muted-foreground text-xs">{label}</span>
      <div className="flex-1 h-5 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full flex items-center justify-end pr-2`} style={{ width: `${Math.max(pct, 2)}%` }}>
          <span className="text-[10px] font-medium text-white">{count}</span>
        </div>
      </div>
      <span className="w-12 text-right text-xs text-muted-foreground">{pct.toFixed(1)}%</span>
    </div>
  );
}

export default function StudyStatsPage() {
  const { token } = useAuthStore();
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);
  const [period, setPeriod] = useState("day");

  const fetchData = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await fetchStudyStats(token, { days, period });
      setStats(data);
    } catch (e) {
      console.error("Failed to fetch study stats:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [token, days, period]);

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const { summary } = stats;
  const totalRatings = (summary.rating_distribution.again + summary.rating_distribution.hard +
    summary.rating_distribution.good + summary.rating_distribution.easy) || 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BookOpen className="h-6 w-6" /> 学习统计
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
          <select
            className="border rounded-md px-2 py-1 text-sm bg-background"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          >
            <option value="day">按天</option>
            <option value="week">按周</option>
            <option value="month">按月</option>
          </select>
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={BarChart3}
          label="总复习次数"
          value={summary.total_reviews}
          color="text-primary"
          tooltip="选定时间段内所有卡片的复习总次数。每次回答一张卡片计一次复习。"
        />
        <StatCard
          icon={Target}
          label="保留率"
          value={`${(summary.retention_rate * 100).toFixed(1)}%`}
          sub={summary.retention_rate >= 0.9 ? "🎯 优秀！保持即可" : summary.retention_rate >= 0.8 ? "👍 良好，继续保持" : "⚠️ 需加油，建议减少新卡量"}
          color={summary.retention_rate >= 0.9 ? "text-green-500" : summary.retention_rate >= 0.8 ? "text-yellow-500" : "text-red-500"}
          tooltip="复习时评为 Good 或 Easy 的比例。≥90% 优秀，≥80% 良好，<80% 说明遗忘较多，建议减少每天的新卡数量或增加复习频率。"
        />
        <StatCard
          icon={Award}
          label="连续天数"
          value={`${summary.streak_days}天`}
          sub={`${summary.total_sessions}次学习`}
          color="text-orange-500"
          tooltip="连续每天至少完成一次复习的天数。中断一天会重新计数。坚持打卡有助于形成学习习惯。"
        />
        <StatCard
          icon={Clock}
          label="学习时间"
          value={`${Math.round(summary.total_time_ms / 60000)}分`}
          sub={`平均 ${summary.avg_session_cards} 卡/次`}
          color="text-blue-500"
          tooltip="选定时间段内总学习时长，以及每次学习平均复习的卡片数量。"
        />
      </div>

      {/* Daily review chart */}
      {period === "day" && stats.daily && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Calendar className="h-4 w-4" /> 每日复习趋势
              <span className="relative group">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                <span className="absolute bottom-full left-0 mb-1 w-56 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                  绿色=回答正确（Good/Easy），红色=回答错误（Again）。柱子越高表示该天复习次数越多，红色比例越低越好。
                </span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DailyReviewChart data={stats.daily} />
          </CardContent>
        </Card>
      )}

      {/* Aggregated table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            {period === "day" ? "每日明细" : period === "week" ? "每周汇总" : "每月汇总"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AggregatedTable data={stats.aggregated} period={period} />
        </CardContent>
      </Card>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Rating distribution */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Brain className="h-4 w-4" /> 评分分布
              <span className="relative group">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                <span className="absolute bottom-full left-0 mb-1 w-60 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                  忘记=完全忘记需重学，困难=犹豫想起，记住=顺利回忆，简单=非常简单。记住+简单的占比即保留率，忘记比例越低越好。
                </span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <RatingBar label="忘记" count={summary.rating_distribution.again} total={totalRatings} color="bg-red-500" />
            <RatingBar label="困难" count={summary.rating_distribution.hard} total={totalRatings} color="bg-orange-500" />
            <RatingBar label="记住" count={summary.rating_distribution.good} total={totalRatings} color="bg-green-500" />
            <RatingBar label="简单" count={summary.rating_distribution.easy} total={totalRatings} color="bg-blue-500" />
          </CardContent>
        </Card>

        {/* Card states */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Zap className="h-4 w-4" /> 卡片状态
              <span className="relative group">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                <span className="absolute bottom-full right-0 mb-1 w-56 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                  新卡=从未学过，学习中=初次学习还没毕业，复习中=已进入间隔重复周期，重学中=之前记住但遗忘后重新学习。
                </span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(summary.cards_by_state).map(([state, count]) => {
                const labels: Record<string, string> = {
                  unseen: "未学习", new: "新卡", learning: "学习中",
                  review: "复习中", relearning: "重学中",
                };
                const colors: Record<string, string> = {
                  unseen: "bg-gray-400", new: "bg-blue-500", learning: "bg-yellow-500",
                  review: "bg-green-500", relearning: "bg-red-400",
                };
                return (
                  <div key={state} className="flex items-center gap-2 text-sm">
                    <div className={`w-3 h-3 rounded ${colors[state] || "bg-gray-400"}`} />
                    <span className="w-16 text-muted-foreground text-xs">{labels[state] || state}</span>
                    <span className="font-mono text-xs">{String(count)}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* By category */}
      {stats.by_category && stats.by_category.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BookOpen className="h-4 w-4" /> 按分类统计
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted-foreground border-b">
                    <th className="text-left py-2">分类</th>
                    <th className="text-right py-2">复习次数</th>
                    <th className="text-right py-2">保留率</th>
                    <th className="text-right py-2">学习时间</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.by_category.map((cat: any, i: number) => (
                    <tr key={i} className="border-b hover:bg-muted/50">
                      <td className="py-2">{cat.category}</td>
                      <td className="text-right">{cat.reviews}</td>
                      <td className={`text-right ${cat.retention >= 0.9 ? "text-green-500" : cat.retention >= 0.7 ? "text-yellow-500" : "text-red-500"}`}>
                        {(cat.retention * 100).toFixed(1)}%
                      </td>
                      <td className="text-right">{Math.round((cat.time_ms || 0) / 60000)}分</td>
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
