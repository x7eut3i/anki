"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { quiz as quizApi, categories as catApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  ClipboardCheck,
  ArrowLeft,
  ArrowRight,
  Trophy,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { isHiddenTag, ArticleSourceLink } from "@/components/card-detail";
import Link from "next/link";
import { useSwipe } from "@/hooks/use-swipe";

type QuizQuestion = {
  question_id: number;
  card_id: number;
  question_type: string;
  question: string;
  choices: string[] | null;
  category_name: string;
  time_limit: number;
  tags_list?: { id: number; name: string; color: string }[];
};

export default function QuizPage() {
  const { token } = useAuthStore();
  const [cats, setCats] = useState<any[]>([]);
  const [selectedCats, setSelectedCats] = useState<number[]>([]);
  const [questionCount, setQuestionCount] = useState(20);
  const [quizStarted, setQuizStarted] = useState(false);
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [currentQ, setCurrentQ] = useState(0);
  const [answers, setAnswers] = useState<Record<number, { card_id: number; answer: string }>>({});
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(0);

  useEffect(() => {
    if (!token) return;
    catApi.listAll(token).then((data) => {
      // Merge real categories + AI decks (AI decks already have negative IDs)
      setCats([...(data.categories || []), ...(data.ai_categories || [])]);
    });
  }, [token]);

  const startQuiz = async () => {
    if (!token) return;
    setLoading(true);
    try {
      // Separate real category IDs (positive) from deck pseudo-IDs (negative)
      const catIds = selectedCats.filter((id) => id > 0);
      const deckIds = selectedCats.filter((id) => id < 0).map((id) => -id);
      const data = await quizApi.generate(
        {
          category_ids: catIds.length > 0 ? catIds : undefined,
          deck_ids: deckIds.length > 0 ? deckIds : undefined,
          card_count: questionCount,
          include_types: ["choice"],  // Mock test = 100% multiple choice
        },
        token
      );
      setQuestions(data.questions || []);
      setSessionId(data.session_id || 0);
      setQuizStarted(true);
      setCurrentQ(0);
      setAnswers({});
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const selectAnswer = (questionId: number, cardId: number, answer: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: { card_id: cardId, answer } }));
  };

  const submitQuiz = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await quizApi.submit(
        sessionId,
        Object.entries(answers).map(([qid, ans]) => ({
          question_id: parseInt(qid),
          card_id: ans.card_id,
          answer: ans.answer,
        })),
        token
      );
      setResult(data);
    } finally {
      setLoading(false);
    }
  };

  // Swipe hook MUST be called unconditionally (Rules of Hooks — before any early return)
  const swipeRef = useSwipe<HTMLDivElement>({
    onSwipeLeft: () => { if (quizStarted && currentQ < questions.length - 1) setCurrentQ((c) => c + 1); },
    onSwipeRight: () => { if (quizStarted && currentQ > 0) setCurrentQ((c) => c - 1); },
  });

  // Config screen
  if (!quizStarted) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">模拟测试</h2>
          <p className="text-muted-foreground">选择分类和题目数量开始测试</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">选择分类</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {cats.map((cat) => (
                <Badge
                  key={cat.id}
                  variant={selectedCats.includes(cat.id) ? "default" : "outline"}
                  className="cursor-pointer text-sm py-1.5 px-3"
                  onClick={() =>
                    setSelectedCats((prev) =>
                      prev.includes(cat.id)
                        ? prev.filter((id) => id !== cat.id)
                        : [...prev, cat.id]
                    )
                  }
                >
                  {cat.icon} {cat.name}                  {cat.card_count != null && (
                    <span className="ml-1 opacity-60">({cat.card_count})</span>
                  )}                </Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              不选择则从所有分类出题
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">题目数量</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              {[10, 20, 50, 100].map((n) => (
                <Button
                  key={n}
                  variant={questionCount === n ? "default" : "outline"}
                  onClick={() => setQuestionCount(n)}
                >
                  {n} 题
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Button className="w-full" size="lg" onClick={startQuiz} disabled={loading}>
          <ClipboardCheck className="mr-2 h-5 w-5" />
          {loading ? "生成中..." : "开始测试"}
        </Button>
      </div>
    );
  }

  // Result screen
  if (result) {
    const score = result.score || 0;
    const total = result.total || questions.length;
    const pct = total > 0 ? (score / total) * 100 : 0;
    const results: any[] = result.results || [];

    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex flex-col items-center gap-4 py-8">
          <div
            className={cn(
              "rounded-full p-6",
              pct >= 80 ? "bg-green-100" : pct >= 60 ? "bg-yellow-100" : "bg-red-100"
            )}
          >
            <Trophy
              className={cn(
                "h-16 w-16",
                pct >= 80
                  ? "text-green-600"
                  : pct >= 60
                  ? "text-yellow-600"
                  : "text-red-600"
              )}
            />
          </div>
          <h2 className="text-3xl font-bold">{pct.toFixed(0)}%</h2>
          <p className="text-muted-foreground">
            {score} / {total} 题正确
          </p>
        </div>

        {/* Detailed results */}
        {results.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">答题详情</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {results.map((r: any, idx: number) => {
                const q = questions.find((q) => q.question_id === r.question_id);
                return (
                  <div key={r.question_id} className={cn(
                    "rounded-lg border p-3",
                    r.correct ? "border-green-200 bg-green-50 dark:bg-green-950/20" : "border-red-200 bg-red-50 dark:bg-red-950/20"
                  )}>
                    <div className="flex items-start gap-2">
                      {r.correct ? (
                        <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0 mt-0.5" />
                      ) : (
                        <XCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium mb-1">{idx + 1}. {q?.question || '—'}</p>
                        {!r.correct && (
                          <p className="text-xs text-red-600">你的答案：{r.user_answer}{q?.choices ? ` (${q.choices[r.user_answer.charCodeAt(0) - 65] || r.user_answer})` : ''}</p>
                        )}
                        <p className="text-xs text-green-700">正确答案：{r.correct_answer}</p>
                        {r.pinyin && (
                          <p className="text-xs text-green-600/70 italic">拼音：{r.pinyin}</p>
                        )}
                        {r.explanation && (
                          <p className="text-xs text-muted-foreground mt-1">{r.explanation}</p>
                        )}
                        {r.source && <div className="mt-1"><ArticleSourceLink sourceUrl={r.source} /></div>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        )}

        <div className="flex gap-3 justify-center">
          <Button variant="outline" onClick={() => { setQuizStarted(false); setResult(null); }}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            重新配置
          </Button>
          <Link href="/dashboard">
            <Button>返回仪表盘</Button>
          </Link>
        </div>
      </div>
    );
  }

  // Question screen
  const q = questions[currentQ];
  if (!q) {
    return (
      <div className="max-w-2xl mx-auto text-center py-16 space-y-4">
        <div className="text-6xl">📭</div>
        <h2 className="text-xl font-bold">没有可用的测试题</h2>
        <p className="text-muted-foreground">
          当前分类下没有可用的卡片来生成测试。<br />
          请检查所选分类是否有已学习的卡片，或尝试选择其他分类。
        </p>
        <div className="flex justify-center gap-3 pt-4">
          <Button variant="outline" onClick={() => { setQuizStarted(false); setResult(null); }}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            重新配置
          </Button>
          <Link href="/dashboard">
            <Button>返回仪表盘</Button>
          </Link>
        </div>
      </div>
    );
  }
  const progress = ((currentQ + 1) / questions.length) * 100;

  return (
    <div className="max-w-2xl mx-auto space-y-4" ref={swipeRef}>
      {/* Progress */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>第 {currentQ + 1} / {questions.length} 题</span>
        <div className="flex flex-wrap items-center gap-1">
          {q.category_name && <Badge variant="secondary">{q.category_name}</Badge>}
          {q.tags_list?.filter(t => !isHiddenTag(t.name)).map(tag => (
            <Badge
              key={tag.id}
              variant="outline"
              className="text-xs"
              style={{ borderColor: tag.color || '#6366f1', color: tag.color || '#6366f1' }}
            >
              🏷️ {tag.name}
            </Badge>
          ))}
        </div>
      </div>
      <Progress value={progress} className="h-2" />

      {/* Question */}
      <Card>
        <CardContent className="pt-6">
          <p className="text-lg font-medium mb-6">{q.question}</p>
          {q.choices && q.choices.length > 0 && (
            <div className="space-y-2">
              {q.choices.map((opt, i) => {
                const letter = String.fromCharCode(65 + i);
                const ans = answers[q.question_id];
                const selected = ans?.answer === letter;
                return (
                  <button
                    key={`${q.question_id}-${i}`}
                    className={cn(
                      "w-full text-left px-4 py-3 rounded-lg border transition-colors",
                      selected
                        ? "bg-primary/10 border-primary"
                        : "hover:bg-muted"
                    )}
                    onClick={() => selectAnswer(q.question_id, q.card_id, letter)}
                  >
                    <span className="font-medium mr-2">{letter}.</span>
                    {opt}
                  </button>
                );
              })}
            </div>
          )}
          {q.question_type === 'qa' && (
            <textarea
              className="w-full px-4 py-3 rounded-lg border focus:border-primary outline-none resize-none min-h-[80px]"
              placeholder="请输入答案..."
              value={answers[q.question_id]?.answer || ''}
              onChange={(e) => selectAnswer(q.question_id, q.card_id, e.target.value)}
            />
          )}
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex justify-between">
        <Button
          variant="outline"
          disabled={currentQ === 0}
          onClick={() => setCurrentQ((c) => c - 1)}
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          上一题
        </Button>

        {currentQ < questions.length - 1 ? (
          <Button onClick={() => setCurrentQ((c) => c + 1)}>
            下一题
            <ArrowRight className="ml-1 h-4 w-4" />
          </Button>
        ) : (
          <Button
            onClick={submitQuiz}
            disabled={loading || Object.keys(answers).length === 0}
            className="bg-green-600 hover:bg-green-700"
          >
            {loading ? "提交中..." : "提交答卷"}
          </Button>
        )}
      </div>
    </div>
  );
}
