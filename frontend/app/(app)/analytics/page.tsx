"use client";

import { useMemo } from "react";
import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";

function monthKey(dateValue: string | null) {
  if (!dateValue) return "Unknown";
  const date = new Date(dateValue);
  return date.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

export default function AnalyticsPage() {
  const { data, isLoading, error } = useMeetings();

  const chartData = useMemo(() => {
    const meetings = data ?? [];
    const byMonth = new Map<string, { name: string; meetings: number; actions: number }>();
    meetings.forEach((meeting) => {
      const key = monthKey(meeting.created_at);
      const entry = byMonth.get(key) ?? { name: key, meetings: 0, actions: 0 };
      entry.meetings += 1;
      entry.actions += meeting.action_items_count || 0;
      byMonth.set(key, entry);
    });
    return Array.from(byMonth.values()).slice(-6);
  }, [data]);

  return (
    <div className="space-y-app-6">
      <div>
        <p className="text-xs uppercase tracking-[0.22em] text-text-tertiary">Analytics</p>
        <h2 className="heading-title mt-2 text-foreground">Meeting performance</h2>
      </div>

      {error ? (
        <div className="rounded-[16px] border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
          Analytics unavailable. Please retry later.
        </div>
      ) : null}

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <SkeletonLoader className="h-64" />
          <SkeletonLoader className="h-64" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-[16px] border border-border bg-surface p-4">
            <p className="text-sm font-semibold text-foreground">Meetings captured</p>
            <div className="mt-4 h-52">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <XAxis dataKey="name" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="meetings" stroke="#FF9F43" strokeWidth={3} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="rounded-[16px] border border-border bg-surface p-4">
            <p className="text-sm font-semibold text-foreground">Action items generated</p>
            <div className="mt-4 h-52">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <XAxis dataKey="name" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} />
                  <Tooltip />
                  <Bar dataKey="actions" fill="#1C1C1C" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
