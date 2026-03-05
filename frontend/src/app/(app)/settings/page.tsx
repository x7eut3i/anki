"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { auth } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Settings, User, Shield, LogOut } from "lucide-react";

export default function SettingsPage() {
  const { token, user, setAuth, logout } = useAuthStore();
  const [profile, setProfile] = useState<any>(null);
  const [dailyGoal, setDailyGoal] = useState(50);
  const [desiredRetention, setDesiredRetention] = useState(0.9);
  const [sessionLimit, setSessionLimit] = useState(50);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    auth.me(token).then((data) => {
      setProfile(data);
      setDailyGoal(data.daily_new_card_limit || 50);
      setDesiredRetention(data.desired_retention || 0.9);
      setSessionLimit(data.session_card_limit || 50);
    });
  }, [token]);

  const handleSave = async () => {
    if (!token) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          daily_new_card_limit: dailyGoal,
          desired_retention: desiredRetention,
          session_card_limit: sessionLimit,
        }),
      });
      if (res.ok) {
        const updated = await res.json();
        setProfile(updated);
        setSaveMsg("设置已保存");
      } else {
        setSaveMsg("保存失败");
      }
    } catch {
      setSaveMsg("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    logout();
    window.location.href = "/login";
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">设置</h2>
        <p className="text-muted-foreground">个人偏好和学习设置</p>
      </div>

      {/* Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <User className="h-5 w-5" />
            个人信息
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">用户名</label>
            <Input value={profile?.username || ""} disabled />
          </div>
          <div>
            <label className="text-sm font-medium">邮箱</label>
            <Input value={profile?.email || ""} disabled />
          </div>
        </CardContent>
      </Card>

      {/* Study preferences */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Settings className="h-5 w-5" />
            学习设置
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">每日新卡数量</label>
            <Input
              type="number"
              value={dailyGoal}
              onChange={(e) => setDailyGoal(parseInt(e.target.value) || 20)}
            />
            <p className="text-xs text-muted-foreground mt-1">
              每天最多学习多少张新卡片
            </p>
          </div>
          <div>
            <label className="text-sm font-medium">每次学习上限</label>
            <Input
              type="number"
              min="10"
              max="200"
              value={sessionLimit}
              onChange={(e) => setSessionLimit(parseInt(e.target.value) || 50)}
            />
            <p className="text-xs text-muted-foreground mt-1">
              每次学习 session 最多包含多少张卡片
            </p>
          </div>
          <div>
            <label className="text-sm font-medium">期望记忆保持率</label>
            <Input
              type="number"
              step="0.01"
              min="0.7"
              max="0.99"
              value={desiredRetention}
              onChange={(e) =>
                setDesiredRetention(parseFloat(e.target.value) || 0.9)
              }
            />
            <p className="text-xs text-muted-foreground mt-1">
              FSRS 目标保持率 (0.7 - 0.99)，越高复习频率越高
            </p>
          </div>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "保存中..." : "保存设置"}
          </Button>
          {saveMsg && (
            <p className={`text-sm ${saveMsg === "设置已保存" ? "text-green-600" : "text-red-500"}`}>
              {saveMsg}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Logout */}
      <Card>
        <CardContent className="py-4">
          <Button variant="destructive" onClick={handleLogout} className="w-full">
            <LogOut className="mr-2 h-4 w-4" />
            退出登录
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
