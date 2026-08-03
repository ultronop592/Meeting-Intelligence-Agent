"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell, LogOut, Rows2, Search, SidebarClose, SidebarOpen, UploadCloud, User as UserIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";

const mobileNav = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/meetings", label: "Meetings" },
  { href: "/analytics", label: "Analytics" },
  { href: "/agent-chat", label: "Agent Chat" },
];

type NavbarProps = {
  collapsed: boolean;
  compactMode: boolean;
  onToggleCollapse: () => void;
  onToggleCompact: () => void;
  onToggleMobile: () => void;
};

export function Navbar({ collapsed, compactMode, onToggleCollapse, onToggleCompact, onToggleMobile }: NavbarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const [searchValue, setSearchValue] = useState("");

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const value = searchValue.trim();
    if (typeof window !== "undefined") {
      localStorage.setItem("mia_global_search", value);
      window.dispatchEvent(new CustomEvent("mia-global-search", { detail: value }));
    }
    const targetBase = pathname?.startsWith("/meetings/") ? pathname : "/meetings";
    router.push(targetBase);
  };

  const userInitial = user?.full_name ? user.full_name.charAt(0).toUpperCase() : user?.email?.charAt(0).toUpperCase() || "U";

  return (
    <div
      className={cn(
        "sticky top-0 z-30 border-b border-border/70 bg-surface/92 backdrop-blur",
        compactMode ? "px-3 py-2 md:px-4 lg:px-6" : "px-4 py-3 md:px-6 lg:px-10"
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={onToggleMobile}
            className="md:hidden"
            aria-label="Open sidebar"
          >
            <SidebarOpen className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onToggleCollapse}
            className="hidden md:inline-flex"
            aria-label="Toggle sidebar"
          >
            {collapsed ? <SidebarOpen className="h-4 w-4" /> : <SidebarClose className="h-4 w-4" />}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onToggleCompact}
            className="hidden md:inline-flex"
            aria-label="Toggle compact mode"
          >
            <Rows2 className="h-4 w-4" />
          </Button>
          <form
            onSubmit={submitSearch}
            className="hidden items-center gap-2 rounded-[12px] border border-border bg-surface-2 px-3 py-2 text-sm text-text-tertiary md:flex"
          >
            <Search className="h-4 w-4" />
            <input
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder={pathname?.startsWith("/meetings/") ? "Filter this meeting" : "Search meetings"}
              className="w-72 bg-transparent text-sm text-foreground outline-none placeholder:text-text-tertiary"
            />
          </form>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/meetings"
            className="inline-flex h-8 items-center rounded-[10px] border border-border bg-surface px-3 text-xs text-foreground hover:bg-surface-2"
            aria-label="Upload a new meeting"
          >
            <UploadCloud className="mr-2 h-4 w-4" /> Upload
          </Link>
          <Button variant="ghost" size="sm" aria-label="Notifications">
            <Bell className="h-4 w-4" />
          </Button>

          {/* User Profile & Logout */}
          {user && (
            <div className="flex items-center gap-2 border-l border-border pl-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-accent/20 text-xs font-semibold text-accent border border-accent/30">
                {userInitial}
              </div>
              <span className="hidden text-xs font-medium text-text-secondary lg:inline-block max-w-[140px] truncate">
                {user.full_name || user.email}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={logout}
                title="Sign Out"
                aria-label="Sign Out"
                className="h-8 w-8 p-0 text-text-tertiary hover:text-red-400"
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 md:hidden">
        <form onSubmit={submitSearch} className="flex w-full items-center gap-2">
          <div className="flex h-8 flex-1 items-center rounded-[10px] border border-border bg-surface-2 px-2">
            <Search className="h-4 w-4 text-text-tertiary" />
            <input
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              placeholder="Search"
              className="w-full bg-transparent px-2 text-xs text-foreground outline-none placeholder:text-text-tertiary"
            />
          </div>
          <Button size="sm" variant="outline" type="submit">
            Go
          </Button>
        </form>
        {mobileNav.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "rounded-full border px-3 py-1 text-xs",
              pathname === item.href
                ? "border-accent bg-accent text-foreground"
                : "border-border bg-surface-2 text-text-secondary"
            )}
          >
            {item.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
