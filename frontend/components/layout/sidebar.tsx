"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CalendarPlus,
  ChartPie,
  LayoutDashboard,
  MessagesSquare,
  Search,
  SlidersHorizontal,
  Sparkles,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/meetings", label: "Meetings", icon: CalendarPlus },
  { href: "/search", label: "Memory & Search", icon: Search },
  { href: "/analytics", label: "Analytics", icon: ChartPie },
  { href: "/agent-chat", label: "Agent Chat", icon: MessagesSquare },
  { href: "/integrations", label: "Integrations", icon: SlidersHorizontal },
];

type SidebarProps = {
  collapsed: boolean;
  compactMode: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
};

function SidebarContent({ collapsed, compactMode }: { collapsed: boolean; compactMode: boolean }) {
  const pathname = usePathname();

  return (
    <>
      <div className={cn("flex items-center gap-2.5 px-2", compactMode && "px-1") }>
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white shadow-xs">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className={cn(collapsed && "hidden")}>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-text-tertiary">
            Meeting Intelligence
          </p>
          <h1 className="text-sm font-semibold tracking-tight text-foreground">AI Workspace</h1>
        </div>
      </div>

      <div className={cn("mt-6 flex flex-1 flex-col gap-1.5", compactMode && "mt-4 gap-1") }>
        {navItems.map((item) => {
          const active = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-xl border px-3 py-2 text-sm transition-all",
                compactMode && "gap-2.5 rounded-lg px-2.5 py-1.5 text-xs",
                active
                  ? "border-accent/35 bg-accent/10 text-foreground font-medium shadow-2xs"
                  : "border-transparent text-text-secondary hover:border-border/60 hover:bg-surface-2 hover:text-foreground"
              )}
              title={collapsed ? item.label : undefined}
            >
              <Icon className={cn("h-4 w-4 shrink-0", active ? "text-accent" : "text-text-tertiary")} />
              <span className={cn(collapsed && "hidden")}>{item.label}</span>
            </Link>
          );
        })}
      </div>

      <div
        className={cn(
          "rounded-[14px] border border-border bg-surface-2 p-3 text-xs text-text-secondary",
          compactMode && "rounded-[12px] p-2",
          collapsed && "hidden"
        )}
      >
        <p className="text-foreground">Plan of the week</p>
        <p className="mt-1">Connect Slack + Calendar to automate follow-ups.</p>
      </div>
    </>
  );
}

export function Sidebar({ collapsed, compactMode, mobileOpen, onCloseMobile }: SidebarProps) {
  return (
    <>
      <aside
        className={cn(
          "hidden border-r border-border/70 bg-surface px-4 py-6 md:flex md:flex-col",
          compactMode && "px-3 py-4",
          collapsed ? "w-20" : compactMode ? "w-56" : "w-64"
        )}
      >
        <SidebarContent collapsed={collapsed} compactMode={compactMode} />
      </aside>

      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/30 transition-opacity md:hidden",
          mobileOpen ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onCloseMobile}
      />
      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-full w-72 flex-col border-r border-border bg-surface px-4 py-6 shadow-xl transition-transform md:hidden",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <button
          type="button"
          className="mb-4 inline-flex h-8 w-8 items-center justify-center rounded-[10px] border border-border"
          onClick={onCloseMobile}
          aria-label="Close sidebar"
        >
          <X className="h-4 w-4" />
        </button>
        <SidebarContent collapsed={false} compactMode={compactMode} />
      </aside>
    </>
  );
}
