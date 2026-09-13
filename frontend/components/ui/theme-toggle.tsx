"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/providers/theme-provider";
import { Button } from "@/components/ui/button";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={toggleTheme}
      className={`h-8 w-8 rounded-[10px] p-0 border border-border bg-surface text-text-secondary hover:bg-surface-2 hover:text-foreground transition-colors ${className || ""}`}
      title={theme === "dark" ? "Switch to light mode" : "Switch to charcoal dark mode"}
      aria-label="Toggle theme"
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4 text-amber-400 transition-transform duration-200 rotate-0" />
      ) : (
        <Moon className="h-4 w-4 text-slate-700 transition-transform duration-200 rotate-0" />
      )}
    </Button>
  );
}
