"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Navbar } from "@/components/layout/navbar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [compactMode, setCompactMode] = useState(true);

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
