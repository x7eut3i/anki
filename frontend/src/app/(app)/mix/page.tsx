"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { categories as catApi, studyPresets } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Shuffle,
  Save,
  Trash2,
  PlayCircle,
  Plus,
  Check,
  X,
  FolderOpen,
  Pencil,
} from "lucide-react";

interface PresetItem {
  id: number;
  name: string;
  icon: string;
  category_ids: number[];
  deck_ids: number[];
  card_count: number;
}

interface CategoryItem {
  id: number;
  name: string;
  card_count: number;
}

const PRESET_ICONS = ["📋", "📚", "🔥", "⭐", "🎯", "💡", "🧠", "📖", "✏️", "🏆"];

export default function MixPage() {
  const { token } = useAuthStore();
  const router = useRouter();

  const [cats, setCats] = useState<CategoryItem[]>([]);
  const [aiCats, setAiCats] = useState<CategoryItem[]>([]);
  const [allDecks, setAllDecks] = useState<any[]>([]);
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Selection state
  const [selectedCatIds, setSelectedCatIds] = useState<Set<number>>(new Set());
  const [selectedDeckIds, setSelectedDeckIds] = useState<Set<number>>(new Set());
  const [cardCount, setCardCount] = useState(30);

  // Exclusive selection mode: "none" | "category" | "deck"
  const selectionMode = selectedCatIds.size > 0 ? "category" : selectedDeckIds.size > 0 ? "deck" : "none";

  // Preset editing state
  const [showSave, setShowSave] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [presetIcon, setPresetIcon] = useState("📋");
  const [editingPresetId, setEditingPresetId] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [catData, presetData] = await Promise.all([
        catApi.listAll(token),
        studyPresets.list(token),
      ]);
      setCats(catData.categories || []);
      setAiCats(catData.ai_categories || []);
      setAllDecks((catData.all_decks || []).filter((d: any) => d.card_count > 0));
      setPresets(presetData || []);
    } catch (e) {
      console.error("Failed to load mix data", e);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Toggle helpers (exclusive: selecting a category clears decks, vice versa)
  const toggleCat = (id: number) => {
    if (selectionMode === "deck") return;
    setSelectedCatIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleDeck = (id: number) => {
    if (selectionMode === "category") return;
    setSelectedDeckIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const totalSelected = selectedCatIds.size + selectedDeckIds.size;

  // Select all / deselect all
  const selectAllCats = () => {
    setSelectedCatIds(new Set(cats.map((c) => c.id)));
    setSelectedDeckIds(new Set());
  };
  const deselectAll = () => {
    setSelectedCatIds(new Set());
    setSelectedDeckIds(new Set());
  };

  // Load a preset
  const loadPreset = (preset: PresetItem) => {
    setSelectedCatIds(new Set(preset.category_ids || []));
    setSelectedDeckIds(new Set(preset.deck_ids || []));
    setCardCount(preset.card_count || 30);
  };

  // Save / update preset
  const savePreset = async () => {
    if (!token || !presetName.trim()) return;
    try {
      const payload = {
        name: presetName.trim(),
        icon: presetIcon,
        category_ids: Array.from(selectedCatIds),
        deck_ids: Array.from(selectedDeckIds),
        card_count: cardCount,
      };
      if (editingPresetId) {
        await studyPresets.update(editingPresetId, payload, token);
      } else {
        await studyPresets.create(payload, token);
      }
      setShowSave(false);
      setPresetName("");
      setEditingPresetId(null);
      await loadData();
    } catch (e) {
      console.error("Failed to save preset", e);
    }
  };

  const deletePreset = async (id: number) => {
    if (!token) return;
    try {
      await studyPresets.delete(id, token);
      await loadData();
    } catch (e) {
      console.error("Failed to delete preset", e);
    }
  };

  const editPreset = (preset: PresetItem) => {
    loadPreset(preset);
    setPresetName(preset.name);
    setPresetIcon(preset.icon);
    setEditingPresetId(preset.id);
    setShowSave(true);
  };

  // Start study
  const startStudy = () => {
    const params = new URLSearchParams();
    params.set("mode", "mix");
    if (selectedCatIds.size > 0) {
      params.set("category", Array.from(selectedCatIds).join(","));
    }
    if (selectedDeckIds.size > 0) {
      params.set("deck_ids", Array.from(selectedDeckIds).join(","));
    }
    params.set("limit", String(cardCount));
    router.push(`/study?${params.toString()}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shuffle className="h-6 w-6 text-purple-500" />
            混合练习
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            自由组合多个分类，打造专属学习计划
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={selectAllCats}>
            全选分类
          </Button>
          <Button variant="outline" size="sm" onClick={deselectAll}>
            清空
          </Button>
        </div>
      </div>

      {/* Saved Presets */}
      {presets.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <FolderOpen className="h-4 w-4" />
              我的预设
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {presets.map((p) => (
                <div
                  key={p.id}
                  className="group flex items-center gap-1 border rounded-lg px-3 py-2 hover:bg-accent cursor-pointer transition-colors"
                  onClick={() => loadPreset(p)}
                >
                  <span className="text-lg">{p.icon}</span>
                  <span className="text-sm font-medium">{p.name}</span>
                  <Badge variant="secondary" className="ml-1 text-xs">
                    {(p.category_ids?.length || 0) + (p.deck_ids?.length || 0)} 个分类
                  </Badge>
                  <Badge variant="outline" className="text-xs">
                    {p.card_count} 张
                  </Badge>
                  <button
                    className="ml-1 opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:text-blue-500"
                    onClick={(e) => {
                      e.stopPropagation();
                      editPreset(p);
                    }}
                    title="编辑预设"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </button>
                  <button
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:text-red-500"
                    onClick={(e) => {
                      e.stopPropagation();
                      deletePreset(p.id);
                    }}
                    title="删除预设"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Category Selection */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">📁 科目分类</CardTitle>
          {selectionMode === "deck" && (
            <p className="text-xs text-muted-foreground">已选择牌组，不可同时选择分类</p>
          )}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {cats.map((cat) => {
              const selected = selectedCatIds.has(cat.id);
              const disabled = selectionMode === "deck";
              return (
                <button
                  key={cat.id}
                  disabled={disabled}
                  className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-left transition-all text-sm min-w-0 ${
                    disabled
                      ? "opacity-40 cursor-not-allowed border-gray-200 dark:border-gray-700"
                      : selected
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 ring-1 ring-blue-500"
                      : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                  }`}
                  onClick={() => toggleCat(cat.id)}
                >
                  {selected ? (
                    <Check className="h-4 w-4 text-blue-500 shrink-0" />
                  ) : (
                    <div className="h-4 w-4 rounded border border-gray-300 dark:border-gray-600 shrink-0" />
                  )}
                  <span className="truncate flex-1">{cat.name}</span>
                  <span className="text-xs text-muted-foreground">{cat.card_count}</span>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Deck Selection */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">📦 牌组选择</CardTitle>
          {selectionMode === "category" && (
            <p className="text-xs text-muted-foreground">已选择分类，不可同时选择牌组</p>
          )}
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {allDecks.map((deck) => {
              const selected = selectedDeckIds.has(deck.id);
              const disabled = selectionMode === "category";
              return (
                <button
                  key={deck.id}
                  disabled={disabled}
                  className={`flex flex-col gap-0.5 px-3 py-2.5 rounded-lg border text-left transition-all text-sm min-w-0 ${
                    disabled
                      ? "opacity-40 cursor-not-allowed border-gray-200 dark:border-gray-700"
                      : selected
                      ? "border-purple-500 bg-purple-50 dark:bg-purple-950 text-purple-700 dark:text-purple-300 ring-1 ring-purple-500"
                      : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                  }`}
                  onClick={() => toggleDeck(deck.id)}
                >
                  <div className="flex items-center gap-2 w-full">
                    {selected ? (
                      <Check className="h-4 w-4 text-purple-500 shrink-0" />
                    ) : (
                      <div className="h-4 w-4 rounded border border-gray-300 dark:border-gray-600 shrink-0" />
                    )}
                    <span className="truncate flex-1">{deck.name}</span>
                    <span className="text-xs text-muted-foreground">{deck.card_count}</span>
                  </div>
                  {deck.category_name && (
                    <span className="text-xs text-muted-foreground ml-6">{deck.category_name}</span>
                  )}
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Card Count + Actions */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            {/* Card count */}
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium whitespace-nowrap">每次练习:</label>
              <div className="flex items-center gap-1">
                {[10, 20, 30, 50].map((n) => (
                  <button
                    key={n}
                    className={`px-2.5 py-1 rounded text-sm transition-colors ${
                      cardCount === n
                        ? "bg-blue-500 text-white"
                        : "bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700"
                    }`}
                    onClick={() => setCardCount(n)}
                  >
                    {n}张
                  </button>
                ))}
                <Input
                  type="number"
                  min={1}
                  max={200}
                  value={cardCount}
                  onChange={(e) => setCardCount(Math.max(1, Math.min(200, parseInt(e.target.value) || 30)))}
                  className="w-16 h-8 text-center text-sm"
                />
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 ml-auto">
              {totalSelected > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setShowSave(true);
                    setEditingPresetId(null);
                    setPresetName("");
                    setPresetIcon("📋");
                  }}
                >
                  <Save className="h-4 w-4 mr-1" />
                  保存预设
                </Button>
              )}
              <Button
                size="sm"
                disabled={totalSelected === 0}
                onClick={startStudy}
                className="bg-gradient-to-r from-purple-500 to-blue-500 hover:from-purple-600 hover:to-blue-600 text-white"
              >
                <PlayCircle className="h-4 w-4 mr-1" />
                开始练习
                {totalSelected > 0 && (
                  <Badge variant="secondary" className="ml-1.5 bg-white/20 text-white text-xs">
                    {totalSelected} 个分类
                  </Badge>
                )}
              </Button>
            </div>
          </div>

          {/* Save preset form */}
          {showSave && (
            <div className="mt-4 p-4 border rounded-lg bg-muted/50 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  {editingPresetId ? "编辑预设" : "保存为预设"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {/* Icon selector */}
                <div className="flex gap-1 flex-wrap">
                  {PRESET_ICONS.map((icon) => (
                    <button
                      key={icon}
                      className={`text-lg p-1 rounded transition-colors ${
                        presetIcon === icon
                          ? "bg-blue-100 dark:bg-blue-900 ring-1 ring-blue-500"
                          : "hover:bg-gray-100 dark:hover:bg-gray-800"
                      }`}
                      onClick={() => setPresetIcon(icon)}
                    >
                      {icon}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  placeholder="预设名称，如：常学、公基重点…"
                  value={presetName}
                  onChange={(e) => setPresetName(e.target.value)}
                  className="flex-1 h-9"
                  onKeyDown={(e) => e.key === "Enter" && savePreset()}
                />
                <Button size="sm" onClick={savePreset} disabled={!presetName.trim()}>
                  <Check className="h-4 w-4 mr-1" />
                  {editingPresetId ? "更新" : "保存"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setShowSave(false);
                    setEditingPresetId(null);
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                已选: {Array.from(selectedCatIds)
                  .map((id) => cats.find((c) => c.id === id)?.name)
                  .filter(Boolean)
                  .concat(
                    Array.from(selectedDeckIds)
                      .map((id) => allDecks.find((d: any) => d.id === id)?.name)
                      .filter(Boolean)
                  )
                  .join("、") || "无"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
