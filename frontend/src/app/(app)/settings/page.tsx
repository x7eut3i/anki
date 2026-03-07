"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { auth } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Settings, User, Shield, LogOut, Globe, KeyRound } from "lucide-react";

const TIMEZONE_OPTIONS = [
  { value: "Asia/Shanghai", label: "中国标准时间 (UTC+8)" },
  { value: "Asia/Tokyo", label: "日本标准时间 (UTC+9)" },
  { value: "Asia/Seoul", label: "韩国标准时间 (UTC+9)" },
  { value: "Asia/Singapore", label: "新加坡时间 (UTC+8)" },
  { value: "Asia/Hong_Kong", label: "香港时间 (UTC+8)" },
  { value: "Asia/Taipei", label: "台北时间 (UTC+8)" },
  { value: "Asia/Kolkata", label: "印度标准时间 (UTC+5:30)" },
  { value: "Asia/Dubai", label: "海湾标准时间 (UTC+4)" },
  { value: "Europe/London", label: "英国时间 (UTC+0/+1)" },
  { value: "Europe/Paris", label: "欧洲中部时间 (UTC+1/+2)" },
  { value: "Europe/Moscow", label: "莫斯科时间 (UTC+3)" },
  { value: "America/New_York", label: "美国东部时间 (UTC-5/-4)" },
  { value: "America/Chicago", label: "美国中部时间 (UTC-6/-5)" },
  { value: "America/Denver", label: "美国山地时间 (UTC-7/-6)" },
  { value: "America/Los_Angeles", label: "美国太平洋时间 (UTC-8/-7)" },
  { value: "Australia/Sydney", label: "澳大利亚东部时间 (UTC+10/+11)" },
  { value: "Pacific/Auckland", label: "新西兰时间 (UTC+12/+13)" },
  { value: "UTC", label: "协调世界时 (UTC)" },
];

export default function SettingsPage() {
  const { token, user, setAuth, logout } = useAuthStore();
  const [profile, setProfile] = useState<any>(null);
  const [dailyGoal, setDailyGoal] = useState(50);
  const [desiredRetention, setDesiredRetention] = useState(0.9);
  const [sessionLimit, setSessionLimit] = useState(50);
  const [userTimezone, setUserTimezone] = useState("Asia/Shanghai");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwSaving, setPwSaving] = useState(false);
  const [pwMsg, setPwMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    auth.me(token).then((data) => {
      setProfile(data);
      setDailyGoal(data.daily_new_card_limit || 50);
      setDesiredRetention(data.desired_retention || 0.9);
      setSessionLimit(data.session_card_limit || 50);
      setUserTimezone(data.timezone || "Asia/Shanghai");
      setEmail(data.email || "");
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
          email: email || undefined,
          daily_new_card_limit: dailyGoal,
          desired_retention: desiredRetention,
          session_card_limit: sessionLimit,
          timezone: userTimezone,
        }),
      });
      if (res.ok) {
        const updated = await res.json();
        setProfile(updated);
        // Save timezone to localStorage for frontend date formatting
        localStorage.setItem("user_timezone", userTimezone);
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
            <Input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
            />
            <p className="text-xs text-muted-foreground mt-1">
              修改后点击下方"保存设置"生效
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Change Password */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            修改密码
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">当前密码</label>
            <Input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="输入当前密码"
            />
          </div>
          <div>
            <label className="text-sm font-medium">新密码</label>
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="至少6个字符"
            />
          </div>
          <div>
            <label className="text-sm font-medium">确认新密码</label>
            <Input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="再次输入新密码"
            />
          </div>
          <Button
            onClick={async () => {
              if (!token) return;
              if (newPassword.length < 6) {
                setPwMsg("新密码至少6个字符");
                return;
              }
              if (newPassword !== confirmPassword) {
                setPwMsg("两次输入的密码不一致");
                return;
              }
              setPwSaving(true);
              setPwMsg(null);
              try {
                await auth.changePassword(currentPassword, newPassword, token);
                setPwMsg("密码修改成功");
                setCurrentPassword("");
                setNewPassword("");
                setConfirmPassword("");
              } catch (err: any) {
                setPwMsg(err.message || "密码修改失败");
              } finally {
                setPwSaving(false);
              }
            }}
            disabled={pwSaving || !currentPassword || !newPassword || !confirmPassword}
          >
            {pwSaving ? "修改中..." : "修改密码"}
          </Button>
          {pwMsg && (
            <p className={`text-sm ${pwMsg === "密码修改成功" ? "text-green-600" : "text-red-500"}`}>
              {pwMsg}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Timezone */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Globe className="h-5 w-5" />
            时区设置
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">显示时区</label>
            <select
              value={userTimezone}
              onChange={(e) => setUserTimezone(e.target.value)}
              className="w-full mt-1 p-2 rounded-md border border-input bg-background text-sm"
            >
              {TIMEZONE_OPTIONS.map((tz) => (
                <option key={tz.value} value={tz.value}>
                  {tz.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground mt-1">
              所有时间显示（卡片、文章、日志等）将使用此时区
            </p>
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
