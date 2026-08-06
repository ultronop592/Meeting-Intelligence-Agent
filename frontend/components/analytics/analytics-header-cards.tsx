"use client";

import { Video, Clock, CheckCircle2, Users } from "lucide-react";
import type { AnalyticsSummaryResponse, AnalyticsParticipantsResponse } from "@/types/api";

interface AnalyticsHeaderCardsProps {
  summary?: AnalyticsSummaryResponse;
  participants?: AnalyticsParticipantsResponse;
  isLoading?: boolean;
}

export function AnalyticsHeaderCards({
  summary,
  participants,
  isLoading,
}: AnalyticsHeaderCardsProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-[16px] border border-border/80 bg-surface/60 p-4"
          />
        ))}
      </div>
    );
  }

  const activeParticipantsCount = participants?.participants?.length || 0;

  const cards = [
    {
      title: "Total Meetings",
      value: summary?.total_meetings ?? 0,
      unit: "captured",
      subtext: `${summary?.last_30_days?.meetings_count ?? 0} in last 30d (${summary?.last_7_days?.meetings_count ?? 0} in 7d)`,
      icon: Video,
      color: "text-accent bg-accent/10 border-accent/20",
    },
    {
      title: "Avg Duration",
      value: summary?.avg_duration_minutes ? `${summary.avg_duration_minutes}m` : "0m",
      unit: "per meeting",
      subtext: "Across all recorded sessions",
      icon: Clock,
      color: "text-foreground bg-surface-2 border-border",
    },
    {
      title: "Action Completion",
      value: `${summary?.completion_rate ?? 0}%`,
      unit: `${summary?.completed_action_items ?? 0} / ${summary?.total_action_items ?? 0} done`,
      subtext: `7d rate: ${summary?.last_7_days?.completion_rate ?? 0}% | 30d rate: ${summary?.last_30_days?.completion_rate ?? 0}%`,
      icon: CheckCircle2,
      color: "text-emerald-700 bg-emerald-500/10 border-emerald-500/20",
    },
    {
      title: "Active Team Load",
      value: activeParticipantsCount,
      unit: "participants",
      subtext: `${summary?.total_action_items ?? 0} total tasks assigned`,
      icon: Users,
      color: "text-indigo-700 bg-indigo-500/10 border-indigo-500/20",
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className="flex flex-col justify-between rounded-[16px] border border-border bg-surface p-4 shadow-xs transition-shadow hover:shadow-md"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary font-medium">
                  {card.title}
                </p>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-2xl font-bold tracking-tight text-foreground">
                    {card.value}
                  </span>
                  <span className="text-xs text-text-tertiary font-medium">{card.unit}</span>
                </div>
              </div>
              <div className={`rounded-xl border p-2.5 ${card.color}`}>
                <Icon className="h-4 w-4" />
              </div>
            </div>
            <div className="mt-3 border-t border-border/60 pt-2 text-[11px] font-medium text-text-secondary">
              {card.subtext}
            </div>
          </div>
        );
      })}
    </div>
  );
}
