"use client";

import { Tag, Sparkles } from "lucide-react";
import type { AnalyticsTopicsResponse } from "@/types/api";

interface RecurringTopicsProps {
  topics?: AnalyticsTopicsResponse;
  isLoading?: boolean;
}

export function RecurringTopics({ topics, isLoading }: RecurringTopicsProps) {
  if (isLoading) {
    return (
      <div className="h-64 animate-pulse rounded-[16px] border border-border bg-surface p-4" />
    );
  }

  const topicList = topics?.topics ?? [];

  return (
    <div className="rounded-[16px] border border-border bg-surface p-5 shadow-xs flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between pb-4 border-b border-border/60">
          <div>
            <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent" />
              Recurring Meeting Topics
            </h3>
            <p className="text-xs text-text-tertiary mt-0.5">
              Top keywords and key subjects extracted across all meetings
            </p>
          </div>
        </div>

        {topicList.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center text-center text-sm text-text-tertiary">
            No recurring topics extracted yet.
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap gap-2">
            {topicList.map((item, idx) => {
              const isTop = idx < 3;
              return (
                <div
                  key={idx}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-all ${
                    isTop
                      ? "border-accent/30 bg-accent/10 text-foreground font-semibold shadow-2xs"
                      : "border-border bg-surface-2/80 text-text-secondary hover:bg-surface-2"
                  }`}
                >
                  <Tag className={`h-3 w-3 ${isTop ? "text-accent" : "text-text-tertiary"}`} />
                  <span>{item.topic}</span>
                  <span
                    className={`ml-1 rounded-md px-1.5 py-0.5 text-[10px] ${
                      isTop ? "bg-accent/20 text-accent-strong" : "bg-border/60 text-text-tertiary"
                    }`}
                  >
                    {item.count}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-border/60 text-[11px] text-text-tertiary flex items-center justify-between">
        <span>Auto-analyzed from meeting summaries</span>
        <span>{topicList.length} keywords</span>
      </div>
    </div>
  );
}
