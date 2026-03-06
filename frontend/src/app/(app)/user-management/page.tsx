"use client";

import { useEffect, useState } from "react";
import { useAuthStore } from "@/lib/store";
import { users as usersApi } from "@/lib/api";
import { formatDateTime } from "@/lib/timezone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Loader2,
  UserPlus,
  ShieldCheck,
  ShieldOff,
  ToggleLeft,
  ToggleRight,
  KeyRound,
  Users,
  X,
  Check,
} from "lucide-react";

interface UserItem {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export default function UserManagementPage() {
  const { token, user: currentUser } = useAuthStore();
  const [userList, setUserList] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ username: "", email: "", password: "", is_admin: false });
  const [adding, setAdding] = useState(false);
  const [resetPwdId, setResetPwdId] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const isAdmin = currentUser?.is_admin;

  const loadUsers = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await usersApi.list(token);
      setUserList(data);
    } catch (err) {
      console.error("Failed to load users:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadUsers(); }, [token]);

  const handleAdd = async () => {
    if (!token || !addForm.username.trim() || !addForm.email.trim() || !addForm.password) return;
    setAdding(true);
    try {
      await usersApi.create(addForm, token);
      setShowAdd(false);
      setAddForm({ username: "", email: "", password: "", is_admin: false });
      loadUsers();
    } catch (err: any) {
      alert("创建失败: " + (err.message || "未知错误"));
    } finally {
      setAdding(false);
    }
  };

  const handleToggle = async (userId: number, currentActive: boolean) => {
    if (!token) return;
    try {
      await usersApi.toggleActive(userId, !currentActive, token);
      loadUsers();
    } catch (err: any) {
      alert(err.message || "操作失败");
    }
  };

  const handleResetPassword = async (userId: number) => {
    if (!token || !newPassword || newPassword.length < 6) {
      alert("密码至少6个字符");
      return;
    }
    try {
      await usersApi.resetPassword(userId, newPassword, token);
      setResetPwdId(null);
      setNewPassword("");
      alert("密码已重置");
    } catch (err: any) {
      alert(err.message || "重置失败");
    }
  };

  if (!isAdmin) {
    return (
      <div className="space-y-6 max-w-4xl mx-auto">
        <h2 className="text-3xl font-bold tracking-tight">用户管理</h2>
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            仅管理员可访问此页面
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Users className="h-8 w-8" />
            用户管理
          </h2>
          <p className="text-muted-foreground">管理系统用户：创建、启用/禁用、重置密码</p>
        </div>
        <Button onClick={() => setShowAdd(!showAdd)}>
          <UserPlus className="mr-1 h-4 w-4" />
          新建用户
        </Button>
      </div>

      {/* Add user form */}
      {showAdd && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">➕ 新建用户</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">用户名 <span className="text-red-500">*</span></label>
                <Input
                  placeholder="username"
                  value={addForm.username}
                  onChange={(e) => setAddForm({ ...addForm, username: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">邮箱 <span className="text-red-500">*</span></label>
                <Input
                  placeholder="user@example.com"
                  value={addForm.email}
                  onChange={(e) => setAddForm({ ...addForm, email: e.target.value })}
                  className="mt-1"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">密码 <span className="text-red-500">*</span></label>
                <Input
                  type="password"
                  placeholder="至少6个字符"
                  value={addForm.password}
                  onChange={(e) => setAddForm({ ...addForm, password: e.target.value })}
                  className="mt-1"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={addForm.is_admin}
                onChange={(e) => setAddForm({ ...addForm, is_admin: e.target.checked })}
                className="h-4 w-4 rounded"
              />
              设为管理员
            </label>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleAdd} disabled={adding || !addForm.username.trim() || !addForm.email.trim() || !addForm.password}>
                {adding ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                创建
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>
                <X className="mr-1 h-4 w-4" /> 取消
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* User list */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : userList.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            暂无用户
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {userList.map((u) => (
            <Card key={u.id} className={!u.is_active ? "opacity-60" : ""}>
              <CardContent className="pt-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium">{u.username}</span>
                      {u.is_admin && (
                        <Badge variant="default" className="text-xs bg-amber-600">
                          <ShieldCheck className="h-3 w-3 mr-1" />
                          管理员
                        </Badge>
                      )}
                      {!u.is_active && (
                        <Badge variant="secondary" className="text-xs">已禁用</Badge>
                      )}
                      {u.id === currentUser?.id && (
                        <Badge variant="outline" className="text-xs">当前用户</Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                    <p className="text-[10px] text-muted-foreground">
                      创建于 {formatDateTime(u.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {u.id !== currentUser?.id && (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title={u.is_active ? "禁用用户" : "启用用户"}
                          onClick={() => handleToggle(u.id, u.is_active)}
                        >
                          {u.is_active ? (
                            <ToggleRight className="h-4 w-4 text-green-600" />
                          ) : (
                            <ToggleLeft className="h-4 w-4 text-muted-foreground" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title="重置密码"
                          onClick={() => { setResetPwdId(resetPwdId === u.id ? null : u.id); setNewPassword(""); }}
                        >
                          <KeyRound className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                {/* Reset password inline */}
                {resetPwdId === u.id && (
                  <div className="mt-3 flex items-center gap-2 border-t pt-3">
                    <Input
                      type="password"
                      placeholder="输入新密码（至少6个字符）"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="h-8 text-sm max-w-xs"
                    />
                    <Button size="sm" className="h-8" onClick={() => handleResetPassword(u.id)} disabled={!newPassword || newPassword.length < 6}>
                      确认重置
                    </Button>
                    <Button size="sm" variant="ghost" className="h-8" onClick={() => { setResetPwdId(null); setNewPassword(""); }}>
                      取消
                    </Button>
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
