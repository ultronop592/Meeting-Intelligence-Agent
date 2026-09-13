"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/providers/theme-provider";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme, mounted } = useTheme();

  // Guard against SSR hydration differences while showing a clean placeholder
  const isDark = mounted ? theme === "dark" : true;

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`group relative inline-flex h-9 items-center gap-2 rounded-xl border border-border bg-surface px-3 text-xs font-semibold text-foreground shadow-2xs hover:bg-surface-2 hover:border-accent/40 active:scale-95 transition-all cursor-pointer select-none ${
        className || ""
      }`}
      title={isDark ? "Switch to Light Mode" : "Switch to Charcoal Dark Mode"}
      aria-label="Toggle theme mode"
    >
      {isDark ? (
        <>
          <span className="flex h-5 w-5 items-center justify-center rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30 transition-transform duration-300 group-hover:rotate-45">
            <Sun className="h-3.5 w-3.5" />
          </span>
          <span className="font-medium text-xs text-foreground tracking-wide">
            Dark
          </span>
        </>
      ) : (
        <>
          <span className="flex h-5 w-5 items-center justify-center rounded-lg bg-slate-200 text-slate-800 border border-slate-300 transition-transform duration-300 group-hover:-rotate-12">
            <Moon className="h-3.5 w-3.5" />
          </span>
          <span className="font-medium text-xs text-foreground tracking-wide">
            Light
          </span>
        </>
      )}
    </button>
  );
}
