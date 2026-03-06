"use client";

import { useEffect, useState, useRef } from "react";
import { useAuthStore } from "@/lib/store";
import { importExport, decks as deckApi, jobs as jobsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Upload,
  Download,
  FileJson,
  FileSpreadsheet,
  CheckCircle2,
  Loader2,
  Clock,
  ExternalLink,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export default function ImportExportPage() {
  const { token } = useAuthStore();
  const [importDecksList, setImportDecksList] = useState<any[]>([]);
  const [exportDecksList, setExportDecksList] = useState<any[]>([]);
  const [selectedImportDeck, setSelectedImportDeck] = useState<number | null>(null);
  const [selectedExportDeck, setSelectedExportDeck] = useState<number | "all" | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [resultType, setResultType] = useState<"success" | "error" | "info">("success");
  const [importing, setImporting] = useState(false);
  const [lastImportCount, setLastImportCount] = useState(0);
  const [allowCorrection, setAllowCorrection] = useState(false);
  const csvRef = useRef<HTMLInputElement>(null);
  const jsonRef = useRef<HTMLInputElement>(null);
  const excelRef = useRef<HTMLInputElement>(null);
  const directRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) return;
    deckApi.list(token).then((d: any[]) => {
      // Import: exclude AI-XXX decks
      setImportDecksList(d.filter((deck) => !deck.name.startsWith("AI-")));
      // Export: all decks
      setExportDecksList(d);
    });
  }, [token]);

  const handleImport = async (type: "csv" | "json" | "excel") => {
    if (!token || !selectedImportDeck) {
      setResult("请先选择导入牌组");
      setResultType("error");
      return;
    }
    const ref = type === "csv" ? csvRef : type === "json" ? jsonRef : excelRef;
    const file = ref.current?.files?.[0];
    if (!file) return;

    setImporting(true);
    setResult(null);

    try {
      const fn = type === "csv" ? importExport.importCSV : type === "json" ? importExport.importJSON : importExport.importExcel;
      const data = await fn(selectedImportDeck, file, token, undefined, allowCorrection);

      // Handle async job response
      if (data.job_id) {
        setResult(`📋 导入任务已提交（任务 #${data.job_id}），AI 正在后台处理...`);
        setResultType("info");

        // Poll for completion
        _pollJob(data.job_id);
      } else {
        // Legacy sync response (shouldn't happen with new backend)
        const count = data.created || data.imported || 0;
        setLastImportCount(count);
        setResult(data.message || `导入成功！已导入 ${count} 张卡片`);
        setResultType("success");
      }
    } catch {
      setResult("导入失败，请检查文件格式");
      setResultType("error");
    } finally {
      setImporting(false);
      if (ref.current) ref.current.value = "";
    }
  };

  const _pollJob = async (jobId: number) => {
    if (!token) return;
    let attempts = 0;
    const maxAttempts = 120; // 2 minutes
    const poll = async () => {
      try {
        const job = await jobsApi.get(jobId, token);
        if (job.status === "completed") {
          const res = job.result_json ? JSON.parse(job.result_json) : {};
          const count = res.created || res.imported || 0;
          setLastImportCount(count);
          setResult(res.message || `✅ 导入完成！已导入 ${count} 张卡片${res.ai_enhanced ? "（AI 增强）" : ""}`);
          setResultType("success");
          return;
        } else if (job.status === "failed") {
          setResult(`❌ 导入失败：${job.error_message || "未知错误"}`);
          setResultType("error");
          return;
        }
        // Still running
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 1000);
        }
      } catch {
        // Ignore poll errors
      }
    };
    setTimeout(poll, 1500);
  };

  const handleDirectImport = async () => {
    if (!token || !selectedImportDeck) {
      setResult("请先选择导入牌组");
      setResultType("error");
      return;
    }
    const file = directRef.current?.files?.[0];
    if (!file) return;

    setImporting(true);
    setResult(null);

    try {
      const data = await importExport.importDirect(selectedImportDeck, file, token);
      const count = data.imported || 0;
      setLastImportCount(count);
      setResult(data.message || `直接导入完成！${count} 张卡片已导入`);
      setResultType("success");
    } catch {
      setResult("直接导入失败，请检查JSON文件格式");
      setResultType("error");
    } finally {
      setImporting(false);
      if (directRef.current) directRef.current.value = "";
    }
  };

  const handleExport = async (type: "csv" | "json") => {
    if (!token || !selectedExportDeck) {
      setResult("请先选择导出牌组");
      setResultType("error");
      return;
    }
    try {
      const fn = type === "csv" ? importExport.exportCSV : importExport.exportJSON;
      const deckId = selectedExportDeck === "all" ? undefined : selectedExportDeck;
      const res = await fn(deckId, token);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = selectedExportDeck === "all" ? `all_cards.${type}` : `deck_${selectedExportDeck}.${type}`;
      a.click();
      URL.revokeObjectURL(url);
      setResult("导出成功！");
      setResultType("success");
    } catch {
      setResult("导出失败");
      setResultType("error");
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">导入 / 导出</h2>
        <p className="text-muted-foreground">管理你的卡片数据</p>
      </div>

      {/* Import */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Upload className="h-5 w-5" />
            导入
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* AI toggle + deck selector */}
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-muted-foreground">选择导入牌组</p>
            <label className="flex items-center gap-1.5 cursor-pointer text-sm select-none">
              <input
                type="checkbox"
                checked={allowCorrection}
                onChange={(e) => setAllowCorrection(e.target.checked)}
                className="rounded border-input h-4 w-4 accent-primary"
              />
              <span className="text-muted-foreground">允许AI修正内容</span>
            </label>
          </div>
          <div>
            <div className="flex flex-wrap gap-2">
              {importDecksList.map((d) => (
                <Badge
                  key={d.id}
                  variant={selectedImportDeck === d.id ? "default" : "outline"}
                  className="cursor-pointer py-1.5 px-3"
                  onClick={() => setSelectedImportDeck(d.id)}
                >
                  {d.name} ({d.card_count || 0})
                </Badge>
              ))}
            </div>
            {importDecksList.length === 0 && (
              <p className="text-sm text-muted-foreground">请先创建牌组</p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-2">
              <input
                ref={csvRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={() => handleImport("csv")}
              />
              <Button
                variant="outline"
                className="w-full h-24 flex-col gap-2"
                onClick={() => csvRef.current?.click()}
                disabled={!selectedImportDeck || importing}
              >
                {importing ? <Loader2 className="h-8 w-8 animate-spin" /> : <FileSpreadsheet className="h-8 w-8" />}
                导入 CSV
              </Button>
            </div>
            <div className="space-y-2">
              <input
                ref={jsonRef}
                type="file"
                accept=".json"
                className="hidden"
                onChange={() => handleImport("json")}
              />
              <Button
                variant="outline"
                className="w-full h-24 flex-col gap-2"
                onClick={() => jsonRef.current?.click()}
                disabled={!selectedImportDeck || importing}
              >
                {importing ? <Loader2 className="h-8 w-8 animate-spin" /> : <FileJson className="h-8 w-8" />}
                导入 JSON
              </Button>
            </div>
            <div className="space-y-2">
              <input
                ref={excelRef}
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={() => handleImport("excel")}
              />
              <Button
                variant="outline"
                className="w-full h-24 flex-col gap-2"
                onClick={() => excelRef.current?.click()}
                disabled={!selectedImportDeck || importing}
              >
                {importing ? <Loader2 className="h-8 w-8 animate-spin text-green-600" /> : <FileSpreadsheet className="h-8 w-8 text-green-600" />}
                导入 Excel
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            上传文件后 AI 自动分析内容并生成标准卡片，支持任意列名和自定义格式。
            勾选「允许AI修正内容」后，AI 会对已有内容进行修正优化；否则只做分析补全。
          </p>

          {/* Direct import (no AI) */}
          <div className="border-t pt-3 mt-3">
            <p className="text-xs font-medium text-muted-foreground mb-2">
              📦 直接导入（不使用AI，匹配导出格式的JSON文件）
            </p>
            <input
              ref={directRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={handleDirectImport}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => directRef.current?.click()}
              disabled={!selectedImportDeck || importing}
            >
              {importing ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <FileJson className="h-3.5 w-3.5 mr-1" />}
              直接导入 JSON
            </Button>
          </div>
          {importing && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 text-blue-700 border border-blue-200">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">正在上传文件...</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Export */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Download className="h-5 w-5" />
            导出
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Export deck selector */}
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-2">选择导出牌组</p>
            <div className="flex flex-wrap gap-2">
              <Badge
                variant={selectedExportDeck === "all" ? "default" : "outline"}
                className="cursor-pointer py-1.5 px-3"
                onClick={() => setSelectedExportDeck("all")}
              >
                全部
              </Badge>
              {exportDecksList.map((d) => (
                <Badge
                  key={d.id}
                  variant={selectedExportDeck === d.id ? "default" : "outline"}
                  className="cursor-pointer py-1.5 px-3"
                  onClick={() => setSelectedExportDeck(d.id)}
                >
                  {d.name} ({d.card_count || 0})
                </Badge>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Button
              variant="outline"
              className="h-24 flex-col gap-2"
              onClick={() => handleExport("csv")}
              disabled={!selectedExportDeck}
            >
              <FileSpreadsheet className="h-8 w-8" />
              导出 CSV
            </Button>
            <Button
              variant="outline"
              className="h-24 flex-col gap-2"
              onClick={() => handleExport("json")}
              disabled={!selectedExportDeck}
            >
              <FileJson className="h-8 w-8" />
              导出 JSON
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Result */}
      {result && (
        <div className={cn(
          "flex items-center gap-2 p-4 rounded-lg",
          resultType === "success" && "bg-green-50 border border-green-200",
          resultType === "error" && "bg-red-50 border border-red-200",
          resultType === "info" && "bg-blue-50 border border-blue-200",
        )}>
          {resultType === "success" && <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />}
          {resultType === "error" && <span className="text-red-500 shrink-0">❌</span>}
          {resultType === "info" && <Clock className="h-5 w-5 text-blue-500 shrink-0 animate-pulse" />}
          <span className="text-sm flex-1">{result}</span>
          {resultType === "info" && (
            <Link href="/ai-stats" className="text-xs text-blue-600 hover:underline flex items-center gap-1 shrink-0">
              查看任务 <ExternalLink className="h-3 w-3" />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
