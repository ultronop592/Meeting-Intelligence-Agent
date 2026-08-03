"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Navbar } from "@/components/layout/navbar";
import { useAuth } from "@/components/providers/auth-provider";
import { Loader2 } from "lucide-react";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { loading } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [compactMode, setCompactMode] = useState(true);

  if (loading) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-accent" />
          <p className="text-xs text-text-tertiary">Authenticating session...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex min-h-screen bg-background ${compactMode ? "compact-ui" : ""}`}>
      <Sidebar
        collapsed={collapsed}
        compactMode={compactMode}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex min-h-screen flex-1 flex-col">
        <Navbar
          collapsed={collapsed}
          compactMode={compactMode}
          onToggleCollapse={() => setCollapsed((value) => !value)}
          onToggleCompact={() => setCompactMode((value) => !value)}
          onToggleMobile={() => setMobileOpen((value) => !value)}
        />
        <main className="app-shell flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}
