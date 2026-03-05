"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { tags as tagsApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tag, Plus, Trash2, Edit2, Save, X, Loader2, Palette, ChevronRight } from "lucide-react";
import Link from "next/link";

const COLOR_OPTIONS = [
  { value: "#3B82F6", label: "蓝色" },
  { value: "#EF4444", label: "红色" },
  { value: "#10B981", label: "绿色" },
  { value: "#F59E0B", label: "黄色" },
  { value: "#8B5CF6", label: "紫色" },
  { value: "#EC4899", label: "粉色" },
  { value: "#06B6D4", label: "青色" },
  { value: "#F97316", label: "橙色" },
  { value: "#6B7280", label: "灰色" },
  { value: "#14B8A6", label: "碧绿" },
];

interface TagItem {
  id: number;
  name: string;
  color: string;
  created_at: string;
  card_count?: number;
  article_count?: number;
}

export default function TagsPage() {
  const { token } = useAuthStore();
  const [tagsList, setTagsList] = useState<TagItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("#3B82F6");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editColor, setEditColor] = useState("");
  const [saving, setSaving] = useState(false);

  const loadTags = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await tagsApi.list(token);
      setTagsList(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTags();
  }, [token]);

  const handleCreate = async () => {
    if (!token || !newName.trim()) return;
    setSaving(true);
    try {
      await tagsApi.create({ name: newName.trim(), color: newColor }, token);
      setNewName("");
      setNewColor("#3B82F6");
      setShowCreate(false);
      loadTags();
    } finally {
      setSaving(false);
    }
  };

  const handleStartEdit = (tag: TagItem) => {
    setEditingId(tag.id);
    setEditName(tag.name);
    setEditColor(tag.color || "#3B82F6");
  };

  const handleSaveEdit = async () => {
    if (!token || editingId === null || !editName.trim()) return;
    setSaving(true);
    try {
      await tagsApi.update(editingId, { name: editName.trim(), color: editColor }, token);
      setEditingId(null);
      loadTags();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!token || !confirm("确定删除此标签？标签与卡片/文章的关联也会被删除。")) return;
    try {
      await tagsApi.delete(id, token);
      loadTags();
    } catch {
      // ignore
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">标签管理</h2>
          <p className="text-muted-foreground">管理自定义标签，为卡片和文章分类</p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus className="mr-2 h-4 w-4" />
          新建标签
        </Button>
      </div>

      {/* Create form */}
      {showCreate && (
        <Card>
          <CardContent className="pt-6 space-y-4">
            <Input
              placeholder="标签名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            />
            <div>
              <p className="text-sm font-medium mb-2">选择颜色</p>
              <div className="flex flex-wrap gap-2">
                {COLOR_OPTIONS.map((c) => (
                  <button
                    key={c.value}
                    onClick={() => setNewColor(c.value)}
                    className={`w-8 h-8 rounded-full border-2 transition-all ${
                      newColor === c.value ? "border-foreground scale-110" : "border-transparent"
                    }`}
                    style={{ backgroundColor: c.value }}
                    title={c.label}
                  />
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge style={{ backgroundColor: newColor, color: "white" }}>
                {newName || "预览"}
              </Badge>
            </div>
            <div className="flex gap-2">
              <Button onClick={handleCreate} disabled={!newName.trim() || saving}>
                {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                创建
              </Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tags list */}
      {tagsList.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3">
            <Tag className="h-12 w-12 text-muted-foreground" />
            <p className="text-muted-foreground">还没有标签，创建一个开始使用吧</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {tagsList.map((tag) => (
            <Card key={tag.id} className="hover:shadow-md transition-shadow">
              <CardContent className="pt-4 pb-4">
                {editingId === tag.id ? (
                  /* Edit mode */
                  <div className="space-y-3">
                    <Input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleSaveEdit()}
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {COLOR_OPTIONS.map((c) => (
                        <button
                          key={c.value}
                          onClick={() => setEditColor(c.value)}
                          className={`w-6 h-6 rounded-full border-2 transition-all ${
                            editColor === c.value ? "border-foreground scale-110" : "border-transparent"
                          }`}
                          style={{ backgroundColor: c.value }}
                        />
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" onClick={handleSaveEdit} disabled={saving || !editName.trim()}>
                        <Save className="mr-1 h-3 w-3" /> 保存
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setEditingId(null)}>
                        <X className="mr-1 h-3 w-3" /> 取消
                      </Button>
                    </div>
                  </div>
                ) : (
                  /* View mode */
                  <div className="flex items-center justify-between">
                    <Link
                      href={`/tag-detail?id=${tag.id}&name=${encodeURIComponent(tag.name)}&color=${encodeURIComponent(tag.color || '')}`}
                      className="flex items-center gap-2 flex-1 min-w-0 hover:opacity-80 transition-opacity cursor-pointer"
                    >
                      <Badge
                        style={{ backgroundColor: tag.color || "#6B7280", color: "white" }}
                        className="text-sm px-3 py-1"
                      >
                        {tag.name}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {tag.card_count ?? 0} 卡片 · {tag.article_count ?? 0} 文章
                      </span>
                      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground ml-auto shrink-0" />
                    </Link>
                    <div className="flex gap-1 shrink-0 ml-2">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={(e) => { e.stopPropagation(); handleStartEdit(tag); }}
                        title="编辑"
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive"
                        onClick={(e) => { e.stopPropagation(); handleDelete(tag.id); }}
                        title="删除"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
