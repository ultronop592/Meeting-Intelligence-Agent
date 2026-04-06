"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarPlus, ChartPie, LayoutDashboard, MessagesSquare, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/meetings", label: "Meetings", icon: CalendarPlus },
  { href: "/analytics", label: "Analytics", icon: ChartPie },
  { href: "/agent-chat", label: "Agent Chat", icon: MessagesSquare },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-64 flex-col border-r border-border bg-surface px-4 py-6 md:flex">
      <div className="flex items-center gap-2 px-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-accent text-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-text-tertiary">
            Meeting Intelligence
          </p>
          <h1 className="text-base font-semibold text-foreground">AI Workspace</h1>
        </div>
      </div>

      <div className="mt-8 flex flex-1 flex-col gap-2">
        {navItems.map((item) => {
          const active = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-[12px] border px-3 py-2 text-sm transition-colors",
                active
                  ? "border-accent bg-surface-3 text-foreground"
                  : "border-transparent text-text-secondary hover:border-border hover:bg-surface-2 hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="rounded-[14px] border border-border bg-surface-2 p-3 text-xs text-text-secondary">
        <p className="text-foreground">Plan of the week</p>
        <p className="mt-1">Connect Slack + Calendar to automate follow-ups.</p>
      </div>
    </aside>
  );
}
