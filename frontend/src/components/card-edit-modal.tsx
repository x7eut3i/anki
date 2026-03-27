"use client";

import React, { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Save, X } from "lucide-react";
import { cards as cardsApi } from "@/lib/api";
import { parseJson } from "@/components/card-detail";

interface CardEditModalProps {
  card: any;
  token: string;
  onSaved: (updatedCard: any) => void;
  onClose: () => void;
}

export function CardEditModal({ card, token, onSaved, onClose }: CardEditModalProps) {
  const meta = parseJson<Record<string, any> | null>(card.meta_info, null);
  const distractors = parseJson<string[]>(card.distractors, []);

  const [editForm, setEditForm] = useState({
    front: card.front || "",
    back: card.back || "",
    explanation: card.explanation || "",
    distractors: distractors.join("\n"),
    tags: card.tags || "",
    source: card.source || "",
    meta_info: meta ? JSON.stringify(meta, null, 2) : "",
  });
  const [saving, setSaving] = useState(false);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const distractorsArr = editForm.distractors
        .split("\n")
        .map((d) => d.trim())
        .filter(Boolean);
      const updateData: Record<string, any> = {
        front: editForm.front,
        back: editForm.back,
        explanation: editForm.explanation,
        distractors: JSON.stringify(distractorsArr),
        source: editForm.source,
      };
      if (editForm.tags !== (card.tags || "")) {
        updateData.tags = editForm.tags;
      }
      if (editForm.meta_info.trim()) {
        try {
          JSON.parse(editForm.meta_info);
          updateData.meta_info = editForm.meta_info;
        } catch {
          alert("meta_info 不是有效的 JSON 格式");
          setSaving(false);
          return;
        }
      } else {
        updateData.meta_info = "";
      }
      const updated = await cardsApi.update(card.id, updateData, token);
      onSaved(updated);
    } catch (err) {
      console.error("Save failed:", err);
      alert("保存失败，请重试");
    } finally {
      setSaving(false);
    }
  }, [editForm, card, token, onSaved]);

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-background rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold text-lg">✏️ 编辑卡片</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="text-sm font-medium mb-1 block">题面 (front)</label>
            <textarea
              className="w-full min-h-[80px] rounded-md border border-input bg-background px-3 py-2 text-sm resize-y"
              value={editForm.front}
              onChange={(e) => setEditForm({ ...editForm, front: e.target.value })}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">答案 (back)</label>
            <textarea
              className="w-full min-h-[60px] rounded-md border border-input bg-background px-3 py-2 text-sm resize-y"
              value={editForm.back}
              onChange={(e) => setEditForm({ ...editForm, back: e.target.value })}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">解析 (explanation)</label>
            <textarea
              className="w-full min-h-[80px] rounded-md border border-input bg-background px-3 py-2 text-sm resize-y"
              value={editForm.explanation}
              onChange={(e) => setEditForm({ ...editForm, explanation: e.target.value })}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">干扰项（每行一个）</label>
            <textarea
              className="w-full min-h-[60px] rounded-md border border-input bg-background px-3 py-2 text-sm resize-y"
              value={editForm.distractors}
              onChange={(e) => setEditForm({ ...editForm, distractors: e.target.value })}
              placeholder="错误选项1&#10;错误选项2&#10;错误选项3"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">标签（逗号分隔）</label>
            <input
              className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={editForm.tags}
              onChange={(e) => setEditForm({ ...editForm, tags: e.target.value })}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">来源 (source)</label>
            <div className="w-full min-h-[36px] rounded-md border border-input bg-muted/50 px-3 py-2 text-sm text-muted-foreground break-all">
              {editForm.source || <span className="italic">无</span>}
            </div>
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">元信息 (meta_info) — JSON</label>
            <textarea
              className="w-full min-h-[240px] rounded-md border border-input bg-background px-3 py-2 text-sm font-mono resize-y"
              value={editForm.meta_info}
              onChange={(e) => setEditForm({ ...editForm, meta_info: e.target.value })}
              placeholder='{"knowledge": "...", "exam_focus": "..."}'
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 p-4 border-t">
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            <Save className="mr-1 h-4 w-4" />
            {saving ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </div>
  );
}
