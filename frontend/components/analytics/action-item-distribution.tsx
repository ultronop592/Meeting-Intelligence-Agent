"use client";

import { CheckCircle, AlertTriangle, Clock, PlayCircle } from "lucide-react";
import type { AnalyticsActionItemsResponse } from "@/types/api";

interface ActionItemDistributionProps {
  actionItems?: AnalyticsActionItemsResponse;
  isLoading?: boolean;
}

export function ActionItemDistribution({
  actionItems,
  isLoading,
}: ActionItemDistributionProps) {
  if (isLoading) {
    return (
      <div className="h-64 animate-pulse rounded-[16px] border border-border bg-surface p-4" />
    );
  }

  const open = actionItems?.total_open ?? 0;
  const inProgress = actionItems?.total_in_progress ?? 0;
  const done = actionItems?.total_done ?? 0;
  const overdue = actionItems?.total_overdue ?? 0;
  const total = open + inProgress + done;

  const getPercentage = (val: number) => (total > 0 ? Math.round((val / total) * 100) : 0);

  const statuses = [
    {
      label: "Done",
      count: done,
      percentage: getPercentage(done),
      icon: CheckCircle,
      color: "bg-emerald-500 text-emerald-700 border-emerald-200",
      barColor: "bg-emerald-500",
    },
    {
      label: "In Progress",
      count: inProgress,
      percentage: getPercentage(inProgress),
      icon: PlayCircle,
      color: "bg-amber-500 text-amber-700 border-amber-200",
      barColor: "bg-amber-500",
    },
    {
      label: "Open",
      count: open,
      percentage: getPercentage(open),
      icon: Clock,
      color: "bg-blue-500 text-blue-700 border-blue-200",
      barColor: "bg-blue-500",
    },
    {
      label: "Overdue",
      count: overdue,
      percentage: total > 0 ? Math.round((overdue / total) * 100) : 0,
      icon: AlertTriangle,
      color: "bg-danger text-danger border-danger/30",
      barColor: "bg-danger",
    },
  ];

  return (
    <div className="rounded-[16px] border border-border bg-surface p-5 shadow-xs">
      <div className="pb-4 border-b border-border/60">
        <h3 className="text-base font-semibold text-foreground">
          Action Item Status Breakdown
        </h3>
        <p className="text-xs text-text-tertiary mt-0.5">
          Distribution of action items across state and due dates
        </p>
      </div>

      {total === 0 ? (
        <div className="flex h-44 flex-col items-center justify-center text-center text-sm text-text-tertiary">
          No action items found.
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          {/* Multi-segment progress bar */}
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-2 p-0.5">
            {done > 0 && (
              <div
                style={{ width: `${getPercentage(done)}%` }}
                className="h-full bg-emerald-500 rounded-l-full transition-all"
              />
            )}
            {inProgress > 0 && (
              <div
                style={{ width: `${getPercentage(inProgress)}%` }}
                className="h-full bg-amber-500 transition-all"
              />
            )}
            {open > 0 && (
              <div
                style={{ width: `${getPercentage(open)}%` }}
                className="h-full bg-blue-500 rounded-r-full transition-all"
              />
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 pt-1">
            {statuses.map((item, idx) => {
              const Icon = item.icon;
              return (
                <div
                  key={idx}
                  className="rounded-xl border border-border/70 bg-surface-2/60 p-3"
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${item.barColor}`} />
                    <span className="text-xs font-medium text-text-secondary">{item.label}</span>
                  </div>
                  <div className="mt-2 flex items-baseline justify-between">
                    <span className="text-xl font-bold text-foreground">{item.count}</span>
                    <span className="text-xs font-semibold text-text-tertiary">
                      {item.percentage}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
