"use client";

import Link from "next/link";
import { Bell, Search, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { usePathname } from "next/navigation";

const mobileNav = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/meetings", label: "Meetings" },
  { href: "/analytics", label: "Analytics" },
  { href: "/agent-chat", label: "Agent Chat" },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <div className="sticky top-0 z-30 border-b border-border bg-surface/90 px-4 py-3 backdrop-blur md:px-6 lg:px-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-2 rounded-[12px] border border-border bg-surface-2 px-3 py-2 text-sm text-text-tertiary md:flex">
            <Search className="h-4 w-4" />
            <span>Search meetings, people, or action items</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" aria-label="Upload a new meeting">
            <UploadCloud className="mr-2 h-4 w-4" /> Upload
          </Button>
          <Button variant="ghost" size="sm" aria-label="Notifications">
            <Bell className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 md:hidden">
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
