"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuthStore } from "@/lib/store";
import { review, categories as catApi, reading } from "@/lib/api";
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
  const [customDecks, setCustomDecks] = useState<any[]>([]);
  const [allDecks, setAllDecks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSession, setActiveSession] = useState<any>(null);
  const [recommendation, setRecommendation] = useState<any>(null);
  const [quizRecovery, setQuizRecovery] = useState<any>(null);

  useEffect(() => {
    if (!token) return;
    const fetchAll = () =>
      Promise.all([
        review.stats(token, getUserTimezone()),
        catApi.listAll(token),
        review.getActiveSession(token).catch(() => null),
        reading.dailyRecommendation(token).catch(() => null),
        review.getActiveQuizSession(token).catch(() => null),
      ])
        .then(([s, catData, session, rec, quizSession]) => {
          setStats(s);
          setCats(catData.categories);
          setAiCats(catData.ai_categories || []);
          setCustomDecks(catData.custom_decks || []);
          setAllDecks(catData.all_decks || []);
          if (rec && rec.id) setRecommendation(rec);
          if (session && !session.is_completed) {
            try {
              const remaining = JSON.parse(session.remaining_card_ids || "[]");
              if (remaining.length > 0) {
                setActiveSession({ ...session, remaining: remaining.length });
              } else {
                setActiveSession(null);
              }
            } catch {
              setActiveSession(null);
            }
          } else {
            setActiveSession(null);
          }
          // Check for active quiz session on server
          if (quizSession && !quizSession.is_completed) {
            setQuizRecovery(quizSession);
          } else {
            setQuizRecovery(null);
          }
          return session;
        });

    fetchAll()
      .then((session) => {
        // If there's an active study session, the user likely navigated here
        // mid-session.  The study page fires a keepalive batch-answer on
        // unmount, but it may not be processed yet.  Re-fetch stats after a
        // short delay so "今日复习" reflects the just-submitted reviews.
        if (session && !session.is_completed) {
          setTimeout(() => {
            review.stats(token, getUserTimezone()).then(setStats).catch(() => {});
          }, 1500);
        }
      })
      .finally(() => setLoading(false));

    // Re-fetch session/stats when the page becomes visible again
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        fetchAll().catch(() => {});
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
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
          <CardContent className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-4">
            <div className="flex items-center gap-3">
              <PlayCircle className="h-6 w-6 sm:h-8 sm:w-8 text-primary animate-pulse shrink-0" />
              <div>
                <p className="font-semibold text-sm sm:text-base">
                  有未完成的{activeSession.mode === "mix" ? "混合练习" : "学习"}
                </p>
                <p className="text-xs sm:text-sm text-muted-foreground">
                  还剩 {activeSession.remaining} 张卡片未完成
                </p>
              </div>
            </div>
            <Link href={activeSession.mode === "mix" ? "/study?mode=mix&resume=1" : "/study?resume=1"}>
              <Button size="sm" className="w-full sm:w-auto">
                <PlayCircle className="mr-2 h-4 w-4" />
                继续{activeSession.mode === "mix" ? "练习" : "学习"}
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}

      {/* Quiz recovery banner */}
      {!activeSession && quizRecovery && (
        <Card className="border-green-500/50 bg-green-50/50 dark:bg-green-950/20">
          <CardContent className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 py-4">
            <div className="flex items-center gap-3">
              <ClipboardCheck className="h-6 w-6 sm:h-8 sm:w-8 text-green-600 animate-pulse shrink-0" />
              <div>
                <p className="font-semibold text-sm sm:text-base">有未完成的模拟测试</p>
                <p className="text-xs sm:text-sm text-muted-foreground">
                  已答 {quizRecovery.cards_reviewed || 0} / {quizRecovery.total_cards || 0} 题
                </p>
              </div>
            </div>
            <Link href="/quiz?resume=1">
              <Button className="bg-green-600 hover:bg-green-700 w-full sm:w-auto" size="sm">
                <ClipboardCheck className="mr-2 h-4 w-4" />
                继续测试
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}

      {/* Daily recommendation */}
      {recommendation && (
        <Card
          className="bg-card border hover:shadow-sm transition-shadow cursor-pointer"
          onClick={() => window.location.href = `/reading?article_id=${recommendation.id}`}
        >
          <CardContent className="py-4">
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-muted-foreground">📖 今日推荐精读</span>
                </div>
                <h3 className="font-medium text-sm truncate">{recommendation.title}</h3>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground mt-1">
                  {recommendation.status && (
                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${
                      recommendation.status === "reading" ? "bg-amber-100 text-amber-700" :
                      recommendation.status === "archived" ? "bg-gray-100 text-gray-500" :
                      "bg-blue-100 text-blue-700"
                    }`}>
                      {recommendation.status === "reading" ? "📖 在读" :
                       recommendation.status === "archived" ? "📦 归档" : "✨ 新"}
                    </span>
                  )}
                  {recommendation.quality_score > 0 && (
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                      recommendation.quality_score >= 9 ? "bg-red-100 text-red-700" :
                      recommendation.quality_score >= 7 ? "bg-orange-100 text-orange-700" :
                      recommendation.quality_score >= 5 ? "bg-blue-100 text-blue-700" :
                      "bg-gray-100 text-gray-600"
                    }`}>
                      ⭐ {recommendation.quality_score}/10
                    </span>
                  )}
                  {recommendation.source_name && <span>{recommendation.source_name}</span>}
                  {recommendation.publish_date && <span>{recommendation.publish_date}</span>}
                  {recommendation.word_count > 0 && <span>{recommendation.word_count} 字</span>}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-2 md:gap-4 lg:grid-cols-4">
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
      <div className="grid grid-cols-3 gap-2 md:gap-4">
        <Link href="/study">
          <Card className="cursor-pointer hover:shadow-md transition-shadow h-full">
            <CardContent className="flex flex-col items-center justify-center py-4 md:py-8 gap-2 md:gap-3">
              <BookOpen className="h-8 w-8 md:h-12 md:w-12 text-primary" />
              <h3 className="font-semibold text-sm md:text-lg">开始复习</h3>
              <p className="text-xs md:text-sm text-muted-foreground text-center hidden md:block">
                {dueCount > 0 ? `${dueCount} 张卡片等待复习` : "今日已完成 🎉"}
              </p>
              <Button className="mt-1 md:mt-2" size="sm">立即学习</Button>
            </CardContent>
          </Card>
        </Link>

        <Link href="/mix">
          <Card className="cursor-pointer hover:shadow-md transition-shadow h-full">
            <CardContent className="flex flex-col items-center justify-center py-4 md:py-8 gap-2 md:gap-3">
              <Brain className="h-8 w-8 md:h-12 md:w-12 text-purple-500" />
              <h3 className="font-semibold text-sm md:text-lg">混合模式</h3>
              <p className="text-xs md:text-sm text-muted-foreground text-center hidden md:block">
                跨分类交叉练习
              </p>
              <Button variant="secondary" className="mt-1 md:mt-2" size="sm">混合学习</Button>
            </CardContent>
          </Card>
        </Link>

        <Link href="/quiz">
          <Card className="cursor-pointer hover:shadow-md transition-shadow h-full">
            <CardContent className="flex flex-col items-center justify-center py-4 md:py-8 gap-2 md:gap-3">
              <ClipboardCheck className="h-8 w-8 md:h-12 md:w-12 text-green-500" />
              <h3 className="font-semibold text-sm md:text-lg">模拟测试</h3>
              <p className="text-xs md:text-sm text-muted-foreground text-center hidden md:block">
                检验学习成果
              </p>
              <Button variant="outline" className="mt-1 md:mt-2" size="sm">开始测试</Button>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* Category section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">📁 科目分类</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
            {cats.map((cat: any) => (
              <Link
                key={cat.id}
                href={`/study?category=${cat.id}`}
                className="flex items-center gap-2 p-2.5 rounded-lg border hover:bg-muted/50 hover:border-primary/50 transition-colors"
              >
                <span className="text-lg">{cat.icon}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{cat.name}</p>
                  <p className="text-xs text-muted-foreground">{cat.card_count || 0} 张</p>
                </div>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Deck section */}
      {allDecks.filter((d: any) => d.card_count > 0).length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">📦 牌组</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
              {allDecks.filter((d: any) => d.card_count > 0).map((deck: any) => (
                <Link
                  key={deck.id}
                  href={`/study?deck=${deck.id}`}
                  className={`flex flex-col gap-0.5 p-2.5 rounded-lg border transition-colors hover:bg-muted/50 hover:border-primary/50 ${
                    deck.is_ai ? "border-dashed" : ""
                  }`}
                >
                  <p className="text-sm font-medium truncate">{deck.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {deck.category_name ? `${deck.category_name} · ` : ""}{deck.card_count} 张
                  </p>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
