"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuthStore } from "@/lib/store";
import { review, categories as catApi } from "@/lib/api";
import { getUserTimezone } from "@/lib/timezone";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  BookOpen,
  TrendingUp,
  Target,
  Calendar,
  Flame,
  Brain,
  ClipboardCheck,
  PlayCircle,
  HelpCircle,
} from "lucide-react";

export default function DashboardPage() {
  const { token, user } = useAuthStore();
  const [stats, setStats] = useState<any>(null);
  const [cats, setCats] = useState<any[]>([]);
  const [aiCats, setAiCats] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSession, setActiveSession] = useState<any>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      review.stats(token, getUserTimezone()),
      catApi.listAll(token),
      review.getActiveSession(token).catch(() => null),
    ])
      .then(([s, catData, session]) => {
        setStats(s);
        setCats(catData.categories);
        setAiCats(catData.ai_categories || []);
        if (session && !session.is_completed) {
          try {
            const remaining = JSON.parse(session.remaining_card_ids || "[]");
            if (remaining.length > 0) {
              setActiveSession({ ...session, remaining: remaining.length });
            }
          } catch {
            // ignore parse errors
          }
        }
      })
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  const todayReviews = stats?.reviewed_today || 0;
  const dailyGoal = stats?.max_daily_calls || 50;
  const streak = stats?.streak_days || 0;
  const retention = stats?.retention_rate || 0;
  const totalCards = stats?.total_cards || 0;
  const dueCount = stats?.cards_due_today || 0;

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div>
        <h2 className="text-3xl font-bold tracking-tight">学习概览</h2>
        <p className="text-muted-foreground">坚持每天复习，离上岸更近一步 💪</p>
      </div>

      {/* Resume session banner */}
      {activeSession && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="flex items-center justify-between py-4">
            <div className="flex items-center gap-3">
              <PlayCircle className="h-8 w-8 text-primary animate-pulse" />
              <div>
                <p className="font-semibold">有未完成的学习</p>
                <p className="text-sm text-muted-foreground">
                  还剩 {activeSession.remaining} 张卡片未完成。开始新学习将自动放弃此会话。
                </p>
              </div>
            </div>
            <Link href="/study?resume=1">
              <Button>
                <PlayCircle className="mr-2 h-4 w-4" />
                继续学习
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              今日复习
              <span className="relative group">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 w-48 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                  今天已完成的复习次数 / 每日目标次数。坚持每天完成复习目标有助于巩固记忆。
                </span>
              </span>
            </CardTitle>
            <BookOpen className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {todayReviews} / {dailyGoal}
            </div>
            <Progress
              value={Math.min((todayReviews / dailyGoal) * 100, 100)}
              className="mt-2"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              连续学习
              <span className="relative group">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 w-48 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                  连续每天至少完成一次复习的天数。中断一天会重新计数。
                </span>
              </span>
            </CardTitle>
            <Flame className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{streak} 天</div>
            <p className="text-xs text-muted-foreground mt-1">保持连续打卡</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              记忆保持率
              <span className="relative group">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 w-56 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                  复习时回答正确（评为 Good 或 Easy）的比例。≥90% 为优秀，≥80% 为良好，&lt;80% 需要加强复习频率或降低新卡数量。
                </span>
              </span>
            </CardTitle>
            <Target className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{(retention * 100).toFixed(1)}%</div>
            <p className={`text-xs mt-1 ${
              retention >= 0.9 ? "text-green-600" : retention >= 0.8 ? "text-yellow-600" : "text-red-600"
            }`}>
              {retention >= 0.9 ? "🎯 优秀！保持即可" : retention >= 0.8 ? "👍 良好，继续努力" : "⚠️ 需加油，建议减少新卡量"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              待复习
              <span className="relative group">
                <HelpCircle className="h-3.5 w-3.5 text-muted-foreground/50 cursor-help" />
                <span className="absolute bottom-full right-0 mb-1 w-52 p-2 rounded-md bg-popover border shadow-lg text-xs text-popover-foreground opacity-0 group-hover:opacity-100 pointer-events-none z-50">
                  根据间隔重复算法(FSRS)计算出今天到期需要复习的卡片数量。及时复习能防止遗忘。
                </span>
              </span>
            </CardTitle>
            <Calendar className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-primary">{dueCount}</div>
            <p className="text-xs text-muted-foreground mt-1">
              共 {totalCards} 张卡片
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Quick actions */}
      <div className="grid gap-4 md:grid-cols-3">
        <Link href="/study">
          <Card className="cursor-pointer hover:shadow-md transition-shadow h-full">
            <CardContent className="flex flex-col items-center justify-center py-8 gap-3">
              <BookOpen className="h-12 w-12 text-primary" />
              <h3 className="font-semibold text-lg">开始复习</h3>
              <p className="text-sm text-muted-foreground text-center">
                {dueCount > 0 ? `${dueCount} 张卡片等待复习` : "今日已完成 🎉"}
              </p>
              <Button className="mt-2">立即学习</Button>
            </CardContent>
          </Card>
        </Link>

        <Link href="/mix">
          <Card className="cursor-pointer hover:shadow-md transition-shadow h-full">
            <CardContent className="flex flex-col items-center justify-center py-8 gap-3">
              <Brain className="h-12 w-12 text-purple-500" />
              <h3 className="font-semibold text-lg">混合模式</h3>
              <p className="text-sm text-muted-foreground text-center">
                跨分类交叉练习
              </p>
              <Button variant="secondary" className="mt-2">混合学习</Button>
            </CardContent>
          </Card>
        </Link>

        <Link href="/quiz">
          <Card className="cursor-pointer hover:shadow-md transition-shadow h-full">
            <CardContent className="flex flex-col items-center justify-center py-8 gap-3">
              <ClipboardCheck className="h-12 w-12 text-green-500" />
              <h3 className="font-semibold text-lg">模拟测试</h3>
              <p className="text-sm text-muted-foreground text-center">
                检验学习成果
              </p>
              <Button variant="outline" className="mt-2">开始测试</Button>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Category overview */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">科目分类</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {cats.map((cat: any) => (
              <div
                key={cat.id}
                className="flex flex-col gap-1 p-3 rounded-lg border hover:bg-muted/50 hover:border-primary/50 transition-colors"
              >
                <Link
                  href={`/study?category=${cat.id}&exclude_ai=1`}
                  className="flex items-center gap-2 cursor-pointer"
                >
                  <span className="text-xl">{cat.icon}</span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{cat.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {cat.card_count || 0} 张可学习
                    </p>
                  </div>
                </Link>
              </div>
            ))}
          </div>

          {/* AI-generated categories */}
          {aiCats.length > 0 && (
            <>
              <div className="flex items-center gap-2 pt-2">
                <span className="text-sm font-medium text-muted-foreground">🤖 AI 生成</span>
                <div className="flex-1 border-t" />
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {aiCats.map((cat: any) => (
                  <div
                    key={cat.id}
                    className="flex flex-col gap-1 p-3 rounded-lg border border-dashed hover:bg-muted/50 hover:border-primary/50 transition-colors"
                  >
                    <Link
                      href={`/study?deck=${cat.deck_id}`}
                      className="flex items-center gap-2 cursor-pointer"
                    >
                      <span className="text-xl">{cat.icon}</span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{cat.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {cat.card_count || 0} 张卡片
                        </p>
                      </div>
                    </Link>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
