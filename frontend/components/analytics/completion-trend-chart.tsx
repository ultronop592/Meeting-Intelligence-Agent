"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TimelineDataPoint } from "@/types/api";

interface CompletionTrendChartProps {
  timeline?: TimelineDataPoint[];
  period: "weekly" | "monthly";
  onPeriodChange: (period: "weekly" | "monthly") => void;
  isLoading?: boolean;
}

export function CompletionTrendChart({
  timeline = [],
  period,
  onPeriodChange,
  isLoading,
}: CompletionTrendChartProps) {
  if (isLoading) {
    return (
      <div className="h-80 animate-pulse rounded-[16px] border border-border bg-surface p-4" />
    );
  }

  return (
    <div className="rounded-[16px] border border-border bg-surface p-5 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-border/60">
        <div>
          <h3 className="text-base font-semibold text-foreground">
            Meeting & Action Trend
          </h3>
          <p className="text-xs text-text-tertiary mt-0.5">
            Meeting frequency vs. completed action items over time
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border bg-surface-2 p-1 text-xs">
          <button
            onClick={() => onPeriodChange("weekly")}
            className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
              period === "weekly"
                ? "bg-surface text-foreground shadow-xs"
                : "text-text-tertiary hover:text-foreground"
            }`}
          >
            Weekly
          </button>
          <button
            onClick={() => onPeriodChange("monthly")}
            className={`rounded-md px-2.5 py-1 font-medium transition-colors ${
              period === "monthly"
                ? "bg-surface text-foreground shadow-xs"
                : "text-text-tertiary hover:text-foreground"
            }`}
          >
            Monthly
          </button>
        </div>
      </div>

      {timeline.length === 0 ? (
        <div className="flex h-56 flex-col items-center justify-center text-center text-sm text-text-tertiary">
          No meeting trend data available for this timeframe.
        </div>
      ) : (
        <div className="mt-4 h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={timeline} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="meetingsGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#FF9F43" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#FF9F43" stopOpacity={0.0} />
                </linearGradient>
                <linearGradient id="actionsGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10B981" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#10B981" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E5E5" />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "#7A7A7A" }}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "#7A7A7A" }}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  borderColor: "#E5E5E5",
                  borderRadius: "12px",
                  fontSize: "12px",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                }}
              />
              <Area
                type="monotone"
                dataKey="meetings_count"
                name="Meetings"
                stroke="#FF9F43"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#meetingsGradient)"
              />
              <Area
                type="monotone"
                dataKey="completed_action_items"
                name="Completed Actions"
                stroke="#10B981"
                strokeWidth={2.5}
                fillOpacity={1}
                fill="url(#actionsGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
