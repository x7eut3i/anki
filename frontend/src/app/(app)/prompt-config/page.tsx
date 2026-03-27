"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { prompts as promptsApi, ai as aiApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Pencil,
  RotateCcw,
  Save,
  X,
  Loader2,
  FileText,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { formatDateTime } from "@/lib/timezone";

interface PromptConfig {
  id: number;
  prompt_key: string;
  display_name: string;
  description: string;
  content: string;
  model_override: string;
  is_customized: boolean;
  updated_at: string;
}

export default function PromptsPage() {
  const { token } = useAuthStore();
  const [promptList, setPromptList] = useState<PromptConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editModel, setEditModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);

  const fetchPrompts = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await promptsApi.list(token);
      // Filter out deprecated prompts
      setPromptList(data.filter((p: PromptConfig) => p.prompt_key !== "smart_import" && p.prompt_key !== "batch_enrich"));
    } catch (err) {
      console.error("Failed to load prompts:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchModels = async () => {
    if (!token) return;
    try {
      const config = await aiApi.getConfig(token);
      if (config.api_base_url && config.api_key_set) {
        const result = await aiApi.listModels({ api_base_url: config.api_base_url }, token);
        if (result.success && result.models) {
          setModels(result.models);
        }
      }
    } catch {
      // Ignore — models list is optional
    }
  };

  useEffect(() => {
    fetchPrompts();
    fetchModels();
  }, [token]);

  const startEdit = (prompt: PromptConfig) => {
    setEditingKey(prompt.prompt_key);
    setEditContent(prompt.content);
    setEditModel(prompt.model_override);
  };

  const handleSave = async () => {
    if (!token || !editingKey) return;
    setSaving(true);
    try {
      await promptsApi.update(editingKey, { content: editContent, model_override: editModel }, token);
      setEditingKey(null);
      fetchPrompts();
    } catch (err: any) {
      alert("保存失败: " + (err.message || "未知错误"));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async (key: string) => {
    if (!token || !confirm("确认恢复此提示词为默认内容？自定义内容将丢失。")) return;
    try {
      await promptsApi.reset(key, token);
      if (editingKey === key) setEditingKey(null);
      fetchPrompts();
    } catch (err: any) {
      alert("重置失败: " + (err.message || "未知错误"));
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Prompt 管理</h2>
        <p className="text-muted-foreground">查看和编辑所有 AI 提示词，可为每个 Prompt 指定专用模型</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-4">
          {promptList.map((prompt) => {
            const isEditing = editingKey === prompt.prompt_key;
            const isExpanded = expandedKey === prompt.prompt_key;
            return (
              <Card key={prompt.prompt_key}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-primary" />
                      <CardTitle className="text-base">{prompt.display_name}</CardTitle>
                      {prompt.is_customized && (
                        <Badge variant="secondary" className="text-xs">已自定义</Badge>
                      )}
                      {prompt.model_override && (
                        <Badge variant="outline" className="text-xs">模型: {prompt.model_override}</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      {!isEditing && (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => startEdit(prompt)}>
                            <Pencil className="mr-1 h-3 w-3" /> 编辑
                          </Button>
                          {prompt.is_customized && (
                            <Button variant="ghost" size="sm" onClick={() => handleReset(prompt.prompt_key)}>
                              <RotateCcw className="mr-1 h-3 w-3" /> 恢复默认
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">{prompt.description}</p>
                </CardHeader>
                <CardContent>
                  {isEditing ? (
                    <div className="space-y-3">
                      {/* Model override */}
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">专用模型（留空使用默认模型）</label>
                        <input
                          type="text"
                          list="prompt-model-list"
                          placeholder="如 gpt-4o, claude-3-sonnet-20240229"
                          value={editModel}
                          onChange={(e) => setEditModel(e.target.value)}
                          className="w-full h-9 mt-1 px-3 rounded-md border border-input bg-background text-sm"
                        />
                        <datalist id="prompt-model-list">
                          {models.map((m) => (
                            <option key={m} value={m} />
                          ))}
                        </datalist>
                      </div>

                      {/* Content editor */}
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">提示词内容</label>
                        <textarea
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          className="w-full mt-1 p-3 rounded-md border border-input bg-background text-sm font-mono min-h-[300px] resize-y"
                          spellCheck={false}
                        />
                        <p className="text-[10px] text-muted-foreground mt-1">
                          共 {editContent.length} 字符
                        </p>
                      </div>

                      <div className="flex gap-2">
                        <Button size="sm" onClick={handleSave} disabled={saving}>
                          {saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                          保存
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingKey(null)}>
                          <X className="mr-1 h-4 w-4" /> 取消
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <button
                        className="w-full flex items-center justify-between text-xs text-muted-foreground hover:text-foreground transition-colors"
                        onClick={() => setExpandedKey(isExpanded ? null : prompt.prompt_key)}
                      >
                        <span>
                          {isExpanded ? "收起内容" : `查看内容 (${prompt.content.length} 字符)`}
                        </span>
                        {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      </button>
                      {isExpanded && (
                        <pre className="mt-2 p-3 rounded-md bg-muted text-xs font-mono whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                          {prompt.content}
                        </pre>
                      )}
                      <p className="text-[10px] text-muted-foreground mt-2">
                        更新时间: {formatDateTime(prompt.updated_at)}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
