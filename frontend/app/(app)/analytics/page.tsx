"use client";

import { useState } from "react";
import {
  useAnalyticsSummary,
  useAnalyticsParticipants,
  useAnalyticsTimeline,
  useAnalyticsActionItems,
  useAnalyticsTopics,
} from "@/lib/hooks/use-analytics";
import { AnalyticsHeaderCards } from "@/components/analytics/analytics-header-cards";
import { CompletionTrendChart } from "@/components/analytics/completion-trend-chart";
import { ParticipantActivityChart } from "@/components/analytics/participant-activity-chart";
import { ActionItemDistribution } from "@/components/analytics/action-item-distribution";
import { RecurringTopics } from "@/components/analytics/recurring-topics";
import { OwnerBreakdownTable } from "@/components/analytics/owner-breakdown-table";
import { BarChart3, RefreshCw } from "lucide-react";

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<"weekly" | "monthly">("monthly");

  const summaryQuery = useAnalyticsSummary();
  const participantsQuery = useAnalyticsParticipants();
  const timelineQuery = useAnalyticsTimeline(period);
  const actionItemsQuery = useAnalyticsActionItems();
  const topicsQuery = useAnalyticsTopics();

  const isAnyLoading =
    summaryQuery.isLoading ||
    participantsQuery.isLoading ||
    timelineQuery.isLoading ||
    actionItemsQuery.isLoading ||
    topicsQuery.isLoading;

  const hasError =
    summaryQuery.isError ||
    participantsQuery.isError ||
    timelineQuery.isError ||
    actionItemsQuery.isError ||
    topicsQuery.isError;

  const handleRefetch = () => {
    summaryQuery.refetch();
    participantsQuery.refetch();
    timelineQuery.refetch();
    actionItemsQuery.refetch();
    topicsQuery.refetch();
  };

  return (
    <div className="space-y-app-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-text-tertiary">
            Intelligence Center
          </p>
          <h2 className="heading-title mt-1 text-foreground flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-accent" />
            Cross-Meeting Analytics Dashboard
          </h2>
        </div>
        <button
          onClick={handleRefetch}
          disabled={isAnyLoading}
          className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface px-3.5 py-2 text-xs font-semibold text-foreground shadow-xs transition-colors hover:bg-surface-2 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isAnyLoading ? "animate-spin" : ""}`} />
          Refresh Metrics
        </button>
      </div>

      {hasError ? (
        <div className="rounded-[16px] border border-danger/40 bg-danger/10 p-4 text-sm text-danger flex items-center justify-between">
          <span>Failed to load some analytics metrics. Please retry.</span>
          <button
            onClick={handleRefetch}
            className="underline font-semibold hover:text-danger/80"
          >
            Retry
          </button>
        </div>
      ) : null}

      {/* 1. Header Summary Metric Cards */}
      <AnalyticsHeaderCards
        summary={summaryQuery.data}
        participants={participantsQuery.data}
        isLoading={summaryQuery.isLoading || participantsQuery.isLoading}
      />

      {/* 2. Charts Grid: Trend Chart & Participant Leaderboard */}
      <div className="grid gap-6 lg:grid-cols-2">
        <CompletionTrendChart
          timeline={timelineQuery.data?.timeline}
          period={period}
          onPeriodChange={setPeriod}
          isLoading={timelineQuery.isLoading}
        />
        <ParticipantActivityChart
          participants={participantsQuery.data?.participants}
          isLoading={participantsQuery.isLoading}
        />
      </div>

      {/* 3. Details Grid: Action Items Status Breakdown & Recurring Topics */}
      <div className="grid gap-6 lg:grid-cols-2">
        <ActionItemDistribution
          actionItems={actionItemsQuery.data}
          isLoading={actionItemsQuery.isLoading}
        />
        <RecurringTopics
          topics={topicsQuery.data}
          isLoading={topicsQuery.isLoading}
        />
      </div>

      {/* 4. Owner Breakdown Table */}
      <OwnerBreakdownTable
        owners={actionItemsQuery.data?.by_owner}
        isLoading={actionItemsQuery.isLoading}
      />
    </div>
  );
}
