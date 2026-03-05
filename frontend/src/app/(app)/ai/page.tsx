"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { ai } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Sparkles,
  Settings,
  Wifi,
  WifiOff,
  Send,
  Bot,
  User,
  CheckCircle2,
  Loader2,
  ShieldCheck,
  Plus,
  Trash2,
  Check,
  Pencil,
} from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ConfigProfile {
  id: number;
  name: string;
  api_base_url: string;
  api_key_set: boolean;
  model: string;
  model_pipeline: string;
  model_reading: string;
  max_daily_calls: number;
  import_batch_size: number;
  import_concurrency: number;
  max_tokens: number;
  temperature: number;
  max_retries: number;
  is_enabled: boolean;
  is_active: boolean;
}

export default function AIPage() {
  const { token } = useAuthStore();
  const [tab, setTab] = useState<"config" | "chat">("config");

  // Config profiles
  const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<number | null>(null);
  const [creatingProfile, setCreatingProfile] = useState(false);
  const [newProfileName, setNewProfileName] = useState("");
  const [renamingProfileId, setRenamingProfileId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Config state (for active profile)
  const [endpoint, setEndpoint] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeySet, setApiKeySet] = useState(false);
  const [model, setModel] = useState("");
  const [modelPipeline, setModelPipeline] = useState("");
  const [modelReading, setModelReading] = useState("");
  const [maxCalls, setMaxCalls] = useState(100);
  const [importBatchSize, setImportBatchSize] = useState(30);
  const [importConcurrency, setImportConcurrency] = useState(3);
  const [maxTokens, setMaxTokens] = useState(8192);
  const [temperature, setTemperature] = useState(0.3);
  const [maxRetries, setMaxRetries] = useState(3);
  const [isEnabled, setIsEnabled] = useState(false);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [testingConn, setTestingConn] = useState(false);
  const [saving, setSaving] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<
    { role: "user" | "assistant"; content: string }[]
  >([]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // Load profiles
  const loadProfiles = async () => {
    if (!token) return;
    try {
      const data = await ai.listConfigs(token);
      setProfiles(data);
      const active = data.find((p: ConfigProfile) => p.is_active);
      if (active) {
        setActiveProfileId(active.id);
        loadConfigFromProfile(active);
      } else if (data.length > 0) {
        setActiveProfileId(data[0].id);
        loadConfigFromProfile(data[0]);
      }
    } catch {
      // Fallback to single config
      try {
        const data = await ai.getConfig(token);
        if (data) {
          setProfiles([data]);
          setActiveProfileId(data.id);
          loadConfigFromProfile(data);
        }
      } catch {}
    }
  };

  const loadConfigFromProfile = (p: ConfigProfile) => {
    setEndpoint(p.api_base_url || "");
    setModel(p.model || "");
    setMaxCalls(p.max_daily_calls || 100);
    setImportBatchSize(p.import_batch_size || 30);
    setImportConcurrency(p.import_concurrency || 3);
    setMaxTokens(p.max_tokens || 8192);
    setTemperature(p.temperature ?? 0.3);
    setMaxRetries(p.max_retries ?? 3);
    setApiKeySet(p.api_key_set || false);
    setIsEnabled(p.is_enabled || false);
    setApiKey("");
    setConnected(null);
    setModels([]);
  };

  useEffect(() => { loadProfiles(); }, [token]);

  const handleSwitchProfile = async (profileId: number) => {
    if (!token || profileId === activeProfileId) return;
    try {
      await ai.activateConfig(profileId, token);
      await loadProfiles();
    } catch (err) {
      console.error("Switch profile failed:", err);
    }
  };

  const handleCreateProfile = async () => {
    if (!token || !newProfileName.trim()) return;
    try {
      await ai.createConfig({ name: newProfileName.trim() }, token);
      setNewProfileName("");
      setCreatingProfile(false);
      await loadProfiles();
    } catch (err) {
      console.error("Create profile failed:", err);
    }
  };

  const handleDeleteProfile = async (profileId: number) => {
    if (!token || !confirm("确定删除此配置？")) return;
    try {
      await ai.deleteConfig(profileId, token);
      await loadProfiles();
    } catch (err: any) {
      alert(err.message || "删除失败");
    }
  };

  const handleRenameProfile = async (profileId: number) => {
    if (!token || !renameValue.trim()) return;
    try {
      await ai.renameConfig(profileId, renameValue.trim(), token);
      setRenamingProfileId(null);
      setRenameValue("");
      await loadProfiles();
    } catch (err: any) {
      alert(err.message || "重命名失败");
    }
  };

  const handleSaveConfig = async () => {
    if (!token) return;
    setSaving(true);
    try {
      const payload: any = {
        api_base_url: endpoint,
        model: model,
        max_daily_calls: maxCalls,
        import_batch_size: importBatchSize,
        import_concurrency: importConcurrency,
        max_tokens: maxTokens,
        temperature: temperature,
        max_retries: maxRetries,
        is_enabled: true,
      };
      if (apiKey) {
        payload.api_key = apiKey;
      }
      const result = await ai.saveConfig(payload, token);
      if (result) {
        setApiKeySet(result.api_key_set || apiKeySet);
        setIsEnabled(result.is_enabled);
      }
      setConnected(null);
      await loadProfiles();
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    if (!token || !endpoint || !model) {
      setConnected(false);
      return;
    }
    if (!apiKey && !apiKeySet) {
      setConnected(false);
      return;
    }
    setTestingConn(true);
    try {
      // Send apiKey only if user typed a new one; otherwise send empty to use stored key
      const result = await ai.testConnection(
        { api_base_url: endpoint, api_key: apiKey, model },
        token
      );
      setConnected(result.success);
    } catch {
      setConnected(false);
    } finally {
      setTestingConn(false);
    }
  };

  const handleFetchModels = async () => {
    if (!token || !endpoint) return;
    if (!apiKey && !apiKeySet) return;
    setLoadingModels(true);
    try {
      const result = await ai.listModels(
        { api_base_url: endpoint, api_key: apiKey },
        token
      );
      if (result.success && result.models.length > 0) {
        setModels(result.models);
        if (!model || !result.models.includes(model)) {
          setModel(result.models[0]);
        }
      } else {
        setModels([]);
        alert("未能获取模型列表，请检查 API 地址和 Key 是否正确");
      }
    } catch (err: any) {
      setModels([]);
      alert("获取模型列表失败：" + (err?.message || "请检查 API 地址和 Key 是否正确"));
    } finally {
      setLoadingModels(false);
    }
  };

  const handleChat = async () => {
    if (!token || !input.trim()) return;
    const msg = input.trim();
    setInput("");
    const updatedMessages = [...messages, { role: "user" as const, content: msg }];
    setMessages(updatedMessages);
    setChatLoading(true);
    try {
      // Send full conversation history to AI
      const history = updatedMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const resp = await ai.chat({ message: msg, history }, token);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: resp.response || resp.reply || resp.message || "..." },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "抱歉，AI 回复失败，请检查配置。" },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Sparkles className="h-8 w-8 text-primary" />
          AI 助手
        </h2>
        <p className="text-muted-foreground">配置AI或与AI对话辅助学习</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        <Button
          variant={tab === "config" ? "default" : "outline"}
          onClick={() => setTab("config")}
        >
          <Settings className="mr-2 h-4 w-4" />
          配置
        </Button>
        <Button
          variant={tab === "chat" ? "default" : "outline"}
          onClick={() => setTab("chat")}
        >
          <Bot className="mr-2 h-4 w-4" />
          AI 对话
        </Button>
      </div>

      {/* Config tab */}
      {tab === "config" && (
        <>
          {/* Profile selector */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                📋 配置方案
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {profiles.map((p) => (
                  <div key={p.id} className="flex items-center gap-1">
                    {renamingProfileId === p.id ? (
                      <div className="flex items-center gap-1">
                        <Input
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && handleRenameProfile(p.id)}
                          className="h-7 w-32 text-sm"
                          autoFocus
                        />
                        <Button size="sm" className="h-7 px-2" onClick={() => handleRenameProfile(p.id)} disabled={!renameValue.trim()}>
                          确定
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setRenamingProfileId(null)}>
                          取消
                        </Button>
                      </div>
                    ) : (
                      <>
                        <Badge
                          variant={p.id === activeProfileId ? "default" : "outline"}
                          className={cn(
                            "cursor-pointer text-sm py-1 px-3",
                            p.id === activeProfileId ? "" : "hover:bg-muted"
                          )}
                          onClick={() => handleSwitchProfile(p.id)}
                        >
                          {p.id === activeProfileId && <Check className="h-3 w-3 mr-1" />}
                          {p.name}
                        </Badge>
                        <button
                          className="text-muted-foreground hover:text-foreground transition-colors"
                          onClick={() => { setRenamingProfileId(p.id); setRenameValue(p.name); }}
                          title="重命名此配置"
                        >
                          <Pencil className="h-3 w-3" />
                        </button>
                        {profiles.length > 1 && (
                          <button
                            className="text-muted-foreground hover:text-destructive transition-colors"
                            onClick={() => handleDeleteProfile(p.id)}
                            title="删除此配置"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                ))}
                {creatingProfile ? (
                  <div className="flex items-center gap-1">
                    <Input
                      placeholder="配置名称"
                      value={newProfileName}
                      onChange={(e) => setNewProfileName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleCreateProfile()}
                      className="h-7 w-32 text-sm"
                      autoFocus
                    />
                    <Button size="sm" className="h-7 px-2" onClick={handleCreateProfile} disabled={!newProfileName.trim()}>
                      确定
                    </Button>
                    <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setCreatingProfile(false)}>
                      取消
                    </Button>
                  </div>
                ) : (
                  <Badge
                    variant="outline"
                    className="cursor-pointer text-sm py-1 px-3 border-dashed hover:bg-muted"
                    onClick={() => setCreatingProfile(true)}
                  >
                    <Plus className="h-3 w-3 mr-1" /> 新建
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                切换配置方案以快速在不同 AI 服务之间切换。当前使用的配置会应用到所有 AI 功能。
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                AI 服务配置
                {isEnabled && apiKeySet && (
                  <Badge variant="default" className="bg-green-600 text-xs">
                    <CheckCircle2 className="h-3 w-3 mr-1" />
                    已启用
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium">API 端点</label>
              <Input
                placeholder="https://api.deepseek.com/v1"
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium">API Key</label>
              <div className="relative">
                <Input
                  type="password"
                  placeholder={apiKeySet ? "••••••••（密钥已保存，留空则不修改）" : "sk-..."}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  className={apiKeySet && !apiKey ? "pr-20" : ""}
                />
                {apiKeySet && !apiKey && (
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1 text-green-600">
                    <ShieldCheck className="h-4 w-4" />
                    <span className="text-xs font-medium">已保存</span>
                  </div>
                )}
              </div>
              {apiKeySet && (
                <p className="text-xs text-muted-foreground mt-1">
                  密钥已安全保存在服务器。留空则使用已保存的密钥，输入新值则更新。
                </p>
              )}
            </div>
            <div>
              <label className="text-sm font-medium">模型</label>
              <div className="flex gap-2">
                {models.length > 0 ? (
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  >
                    {models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                ) : (
                  <Input
                    placeholder="deepseek-chat"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                  />
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0 h-10"
                  onClick={handleFetchModels}
                  disabled={loadingModels || !endpoint || (!apiKey && !apiKeySet)}
                >
                  {loadingModels ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "拉取模型"
                  )}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                填写端点和Key后点击"拉取模型"自动获取可用模型列表。如需为不同功能使用不同模型，可在 Prompt 管理页面为每个 Prompt 单独指定模型。
              </p>
            </div>
            <div>
              <label className="text-sm font-medium">每日调用限制</label>
              <Input
                type="number"
                value={maxCalls}
                onChange={(e) => setMaxCalls(parseInt(e.target.value) || 100)}
              />
            </div>
            <div>
              <label className="text-sm font-medium">导入批处理大小</label>
              <Input
                type="number"
                value={importBatchSize}
                onChange={(e) => setImportBatchSize(parseInt(e.target.value) || 30)}
                min={5}
                max={100}
              />
              <p className="text-xs text-muted-foreground mt-1">
                AI 智能导入时每批处理的行数，切换配置时此值随之变化
              </p>
            </div>
            <div>
              <label className="text-sm font-medium">导入并发数</label>
              <Input
                type="number"
                value={importConcurrency}
                onChange={(e) => setImportConcurrency(parseInt(e.target.value) || 3)}
                min={1}
              />
              <p className="text-xs text-muted-foreground mt-1">
                AI 智能导入时同时处理的批次数量，增大可提高导入速度。默认 3
              </p>
            </div>
            <div>
              <label className="text-sm font-medium">生成最大Token数</label>
              <Input
                type="number"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 8192)}
                min={1}
              />
              <p className="text-xs text-muted-foreground mt-1">
                卡片生成等AI调用的最大输出Token数，防止内容被截断。建议 8192 以上
              </p>
            </div>
            <div>
              <label className="text-sm font-medium">AI 温度 (Temperature)</label>
              <Input
                type="number"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value) || 0.3)}
                min={0}
                max={2}
                step={0.1}
              />
              <p className="text-xs text-muted-foreground mt-1">
                控制AI输出的随机性。0 = 最确定，1 = 较随机。卡片生成建议 0.2-0.3
              </p>
            </div>
            <div>
              <label className="text-sm font-medium">AI 重试次数 (Max Retries)</label>
              <Input
                type="number"
                value={maxRetries}
                onChange={(e) => setMaxRetries(parseInt(e.target.value) || 3)}
                min={1}
                max={10}
              />
              <p className="text-xs text-muted-foreground mt-1">
                AI调用失败后最大重试次数。每次重试间隔递增（指数退避）。默认 3 次
              </p>
            </div>

            <div className="flex gap-2">
              <Button onClick={handleSaveConfig} disabled={saving}>
                {saving ? "保存中..." : "保存配置"}
              </Button>
              <Button
                variant="outline"
                onClick={handleTestConnection}
                disabled={testingConn || !endpoint || !model || (!apiKey && !apiKeySet)}
              >
                {testingConn ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : connected === true ? (
                  <Wifi className="mr-2 h-4 w-4 text-green-500" />
                ) : connected === false ? (
                  <WifiOff className="mr-2 h-4 w-4 text-red-500" />
                ) : (
                  <Wifi className="mr-2 h-4 w-4" />
                )}
                测试连接
              </Button>
            </div>

            {connected === true && (
              <div className="flex items-center gap-2 text-green-600 text-sm">
                <CheckCircle2 className="h-4 w-4" />
                连接成功
              </div>
            )}
            {connected === false && (
              <div className="flex items-center gap-2 text-red-600 text-sm">
                <WifiOff className="h-4 w-4" />
                连接失败，请检查配置
              </div>
            )}

            <div className="mt-4 p-4 rounded-lg bg-muted text-sm space-y-2">
              <p className="font-medium">支持的 AI 服务：</p>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                <li>DeepSeek (推荐中文) — api.deepseek.com/v1</li>
                <li>通义千问 Qwen — dashscope.aliyuncs.com/v1</li>
                <li>OpenAI — api.openai.com/v1</li>
                <li>任何 OpenAI 兼容接口</li>
              </ul>
            </div>
          </CardContent>
        </Card>
        </>
      )}

      {/* Chat tab */}
      {tab === "chat" && (
        <Card className="flex flex-col" style={{ height: "calc(100vh - 280px)" }}>
          <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
                <Bot className="h-12 w-12" />
                <p>向 AI 助手提问学习相关问题</p>
                <div className="flex flex-wrap gap-2 mt-4">
                  {["什么是行政法的基本原则？", "帮我区分故意和过失", "简述马哲唯物辩证法"].map(
                    (q) => (
                      <Badge
                        key={q}
                        variant="outline"
                        className="cursor-pointer"
                        onClick={() => setInput(q)}
                      >
                        {q}
                      </Badge>
                    )
                  )}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn(
                  "flex gap-3",
                  m.role === "user" ? "justify-end" : ""
                )}
              >
                {m.role === "assistant" && (
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <Bot className="h-4 w-4 text-primary" />
                  </div>
                )}
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg px-4 py-3 text-sm",
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  )}
                >
                  {m.role === "assistant" ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 [&_pre]:bg-background/50 [&_pre]:p-3 [&_pre]:rounded [&_code]:text-xs [&_table]:text-xs [&_li]:my-0.5">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap">{m.content}</p>
                  )}
                </div>
                {m.role === "user" && (
                  <div className="h-8 w-8 rounded-full bg-secondary flex items-center justify-center shrink-0">
                    <User className="h-4 w-4" />
                  </div>
                )}
              </div>
            ))}
            {chatLoading && (
              <div className="flex gap-3">
                <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                  <Bot className="h-4 w-4 text-primary" />
                </div>
                <div className="bg-muted rounded-lg px-4 py-3">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              </div>
            )}
          </CardContent>
          <div className="border-t p-4 flex gap-2">
            <Input
              placeholder="输入你的问题..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleChat()}
            />
            <Button onClick={handleChat} disabled={chatLoading || !input.trim()} title="发送">
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
