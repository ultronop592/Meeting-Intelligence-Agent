"use client";

import { useMemo } from "react";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { MeetingCard } from "@/components/meeting/meeting-card";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  const { data, isLoading, error, refetch } = useMeetings();

  const tools = [
    {
      name: "Email Tool",
      purpose: "Sends personalized follow-up emails to participants.",
      useFor: "Use this when each owner should only see their own action items.",
    },
    {
      name: "Slack Tool",
      purpose: "Posts meeting summaries and action items to Slack.",
      useFor: "Use this for fast team visibility in your shared channel.",
    },
    {
      name: "Jira Tool",
      purpose: "Creates Jira tickets from extracted action items.",
      useFor: "Use this when tasks should immediately enter engineering workflow.",
    },
    {
      name: "Calendar Tool",
      purpose: "Books follow-up meetings in Google Calendar.",
      useFor: "Use this to schedule review checkpoints after key meetings.",
    },
  ];

  const metrics = useMemo(() => {
    const meetings = data ?? [];
    const totalMeetings = meetings.length;
    const totalActionItems = meetings.reduce(
      (sum, meeting) => sum + (meeting.action_items_count || 0),
      0
    );
    const minutes = meetings.reduce(
      (sum, meeting) => sum + (meeting.duration_minutes || 0),
      0
    );
    return { totalMeetings, totalActionItems, minutes };
  }, [data]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.22em] text-text-tertiary">
          Overview
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-foreground">
          Your meeting intelligence hub
        </h2>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-[16px] border border-border bg-surface p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Meetings</p>
          <p className="mt-3 text-2xl font-semibold text-foreground">{metrics.totalMeetings}</p>
          <p className="text-xs text-text-secondary">Tracked this month</p>
        </div>
        <div className="rounded-[16px] border border-border bg-surface p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Action items</p>
          <p className="mt-3 text-2xl font-semibold text-foreground">{metrics.totalActionItems}</p>
          <p className="text-xs text-text-secondary">Pending follow-ups</p>
        </div>
        <div className="rounded-[16px] border border-border bg-surface p-4">
          <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Time captured</p>
          <p className="mt-3 text-2xl font-semibold text-foreground">{metrics.minutes} min</p>
          <p className="text-xs text-text-secondary">Across all meetings</p>
        </div>
      </div>

      <div>
        <h3 className="text-lg font-semibold text-foreground">Automation tools</h3>
        <p className="mt-1 text-sm text-text-secondary">
          Built-in backend tools available in this workspace.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {tools.map((tool) => (
          <div key={tool.name} className="rounded-[16px] border border-border bg-surface p-4">
            <p className="text-sm font-semibold text-foreground">{tool.name}</p>
            <p className="mt-2 text-sm text-text-secondary">{tool.purpose}</p>
            <p className="mt-2 text-xs text-text-tertiary">{tool.useFor}</p>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-foreground">Recent meetings</h3>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      {error ? (
        <div className="rounded-[16px] border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
          Could not load meetings. Please retry.
        </div>
      ) : null}

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <SkeletonLoader key={index} className="h-40" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(data ?? []).slice(0, 6).map((meeting) => (
            <MeetingCard key={meeting.id} meeting={meeting} />
          ))}
        </div>
      )}
    </div>
  );
}
