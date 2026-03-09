"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  BookOpen,
  LayoutDashboard,
  Library,
  Brain,
  ClipboardCheck,
  Upload,
  Settings,
  Sparkles,
  LogOut,
  BookMarked,
  PlusCircle,
  Globe,
  FileText,
  Zap,
  Users,
  MoreHorizontal,
  X,
  ScrollText,
  BarChart3,
  ChevronDown,
  ChevronRight,
  Database,
  Monitor,
  TrendingUp,
  Tag,
  Shuffle,
} from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { Button } from "@/components/ui/button";

interface NavItem {
  href: string;
  label: string;
  icon: any;
}

interface NavGroup {
  label: string;
  icon: any;
  items: NavItem[];
  defaultOpen?: boolean;
}

const navGroups: NavGroup[] = [
  {
    label: "学习",
    icon: BookOpen,
    defaultOpen: true,
    items: [
      { href: "/dashboard", label: "仪表盘", icon: LayoutDashboard },
      { href: "/mix", label: "混合练习", icon: Shuffle },
      { href: "/quiz", label: "模拟测试", icon: ClipboardCheck },
      { href: "/reading", label: "文章精读", icon: BookMarked },
      { href: "/study-stats", label: "学习统计", icon: TrendingUp },
    ],
  },
  {
    label: "卡片管理",
    icon: Library,
    defaultOpen: false,
    items: [
      { href: "/decks", label: "牌组管理", icon: Library },
      { href: "/create-cards", label: "添加卡片", icon: PlusCircle },
      { href: "/tags", label: "标签管理", icon: Tag },
      { href: "/import-export", label: "导入导出", icon: Upload },
    ],
  },
  {
    label: "文章抓取",
    icon: Globe,
    defaultOpen: false,
    items: [
      { href: "/sources", label: "来源管理", icon: Globe },
      { href: "/ingestion", label: "自动抓取", icon: Zap },
    ],
  },
  {
    label: "AI管理",
    icon: Sparkles,
    defaultOpen: false,
    items: [
      { href: "/ai", label: "AI助手", icon: Sparkles },
      { href: "/jobs", label: "AI任务", icon: Zap },
      { href: "/ai-stats", label: "AI统计", icon: BarChart3 },
      { href: "/prompt-config", label: "Prompt管理", icon: FileText },
    ],
  },
  {
    label: "系统",
    icon: Monitor,
    defaultOpen: false,
    items: [
      { href: "/logs", label: "日志查看", icon: ScrollText },
      { href: "/user-management", label: "用户管理", icon: Users },
      { href: "/settings", label: "设置", icon: Settings },
    ],
  },
];

// Flat list for mobile nav
const allNavItems = navGroups.flatMap((g) => g.items);

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const [moreOpen, setMoreOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    navGroups.forEach((g) => {
      if (g.defaultOpen) initial.add(g.label);
    });
    return initial;
  });

  // Check if a nav item should be marked active
  const isNavActive = (item: NavItem) => {
    // Exact match or child-path match (href + "/") to avoid
    // prefix collisions like /ai matching /ai-stats
    if (pathname === item.href || pathname.startsWith(item.href + "/")) return true;
    // /tag-detail pages should highlight the 标签管理 (/tags) item
    if (item.href === "/tags" && pathname.startsWith("/tag-detail")) return true;
    return false;
  };

  // Auto-open group containing the active page
  React.useEffect(() => {
    for (const group of navGroups) {
      if (group.items.some((item) => isNavActive(item))) {
        setOpenGroups((prev) => {
          if (prev.has(group.label)) return prev;
          const next = new Set(prev);
          next.add(group.label);
          return next;
        });
        break;
      }
    }
  }, [pathname]);

  const toggleGroup = (label: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(label)) next.delete(label);
      else next.add(label);
      return next;
    });
  };

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 border-r bg-card">
        <div className="flex flex-col flex-1 min-h-0">
          {/* Logo */}
          <div className="flex items-center gap-2 px-6 py-5 border-b">
            <Brain className="h-8 w-8 text-primary" />
            <div>
              <h1 className="font-bold text-lg">Anki Cards</h1>
              <p className="text-xs text-muted-foreground">FSRS智能复习</p>
            </div>
          </div>

          {/* Nav */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
            {navGroups.map((group) => {
              const GroupIcon = group.icon;
              const isOpen = openGroups.has(group.label);
              const hasActive = group.items.some((item) => isNavActive(item));
              return (
                <div key={group.label}>
                  <button
                    onClick={() => toggleGroup(group.label)}
                    className={cn(
                      "flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                      hasActive ? "text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    <GroupIcon className="h-4 w-4" />
                    <span className="flex-1 text-left">{group.label}</span>
                    {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  </button>
                  {isOpen && (
                    <div className="ml-2 mt-0.5 space-y-0.5">
                      {group.items.map((item) => {
                        const Icon = item.icon;
                        const active = isNavActive(item);
                        return (
                          <Link
                            key={item.href}
                            href={item.href}
                            className={cn(
                              "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                              active
                                ? "bg-primary/10 text-primary font-medium"
                                : "text-muted-foreground hover:bg-muted hover:text-foreground"
                            )}
                          >
                            <Icon className="h-4 w-4" />
                            {item.label}
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>

          {/* User */}
          <div className="border-t p-4">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="text-sm font-medium text-primary">
                  {user?.username?.[0]?.toUpperCase() || "U"}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{user?.username || "用户"}</p>
                <p className="text-xs text-muted-foreground truncate">{user?.email || ""}</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => { logout(); window.location.href = "/login"; }}
                title="退出登录"
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 bg-card border-t z-50 safe-area-bottom">
        <div className="flex justify-around py-2">
          {allNavItems.slice(0, 5).map((item) => {
            const Icon = item.icon;
            const active = isNavActive(item);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex flex-col items-center gap-0.5 px-2 py-1 text-xs",
                  active ? "text-primary" : "text-muted-foreground"
                )}
              >
                <Icon className="h-5 w-5" />
                <span>{item.label}</span>
              </Link>
            );
          })}
          {/* More button */}
          <button
            onClick={() => setMoreOpen(true)}
            className={cn(
              "flex flex-col items-center gap-0.5 px-2 py-1 text-xs",
              moreOpen ? "text-primary" : "text-muted-foreground"
            )}
          >
            <MoreHorizontal className="h-5 w-5" />
            <span>更多</span>
          </button>
        </div>
      </nav>

      {/* Mobile "More" drawer */}
      {moreOpen && (
        <div className="md:hidden fixed inset-0 z-[60]">
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/40" onClick={() => setMoreOpen(false)} />
          {/* Panel */}
          <div className="absolute bottom-0 inset-x-0 bg-card rounded-t-2xl border-t max-h-[70vh] overflow-y-auto safe-area-bottom animate-in slide-in-from-bottom duration-200">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <span className="font-semibold text-sm">更多功能</span>
              <button onClick={() => setMoreOpen(false)} className="p-1 rounded-full hover:bg-muted">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-3 space-y-3">
              {navGroups.slice(1).map((group) => {
                const GroupIcon = group.icon;
                return (
                  <div key={group.label}>
                    <div className="flex items-center gap-2 px-2 mb-1">
                      <GroupIcon className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs font-semibold text-muted-foreground">{group.label}</span>
                    </div>
                    <div className="grid grid-cols-4 gap-1">
                      {group.items.map((item) => {
                        const Icon = item.icon;
                        const active = isNavActive(item);
                        return (
                          <Link
                            key={item.href}
                            href={item.href}
                            onClick={() => setMoreOpen(false)}
                            className={cn(
                              "flex flex-col items-center gap-1 p-3 rounded-xl text-xs transition-colors",
                              active
                                ? "bg-primary/10 text-primary"
                                : "text-muted-foreground hover:bg-muted"
                            )}
                          >
                            <Icon className="h-6 w-6" />
                            <span>{item.label}</span>
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* User info (no logout in mobile drawer to prevent accidental taps) */}
            <div className="border-t px-4 py-3 flex items-center gap-3">
              <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="text-sm font-medium text-primary">
                  {user?.username?.[0]?.toUpperCase() || "U"}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{user?.username || "用户"}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
