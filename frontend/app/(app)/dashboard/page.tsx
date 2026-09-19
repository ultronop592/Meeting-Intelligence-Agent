"use client";

import { useMemo } from "react";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { MeetingCard } from "@/components/meeting/meeting-card";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";
import { Button } from "@/components/ui/button";
import { Calendar, CheckSquare, Clock, Mail, MessageSquare, Ticket, Sparkles, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const { data, isLoading, error, refetch } = useMeetings();

  const tools = [
    {
      name: "Email Follow-ups",
      purpose: "Sends personalized follow-up emails with specific action items to each attendee.",
      useFor: "Individual accountability & deadline tracking",
      icon: Mail,
      accent: "text-sky-500 bg-sky-500/10 border-sky-500/20",
    },
    {
      name: "Slack Broadcast",
      purpose: "Posts meeting summaries and extracted action items to team Slack channels.",
      useFor: "Fast team visibility & shared context",
      icon: MessageSquare,
      accent: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20",
    },
    {
      name: "Jira Issue Sync",
      purpose: "Converts extracted action items into prioritized Jira tickets automatically.",
      useFor: "Engineering backlog & sprint workflow",
      icon: Ticket,
      accent: "text-blue-500 bg-blue-500/10 border-blue-500/20",
    },
    {
      name: "Calendar Scheduler",
      purpose: "Books review checkpoints and follow-up syncs in Google Calendar.",
      useFor: "Review milestones & follow-up meetings",
      icon: Calendar,
      accent: "text-amber-500 bg-amber-500/10 border-amber-500/20",
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
    <div className="space-y-app-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-text-tertiary">
            Intelligence Overview
          </p>
          <h2 className="heading-title mt-1 text-foreground">
            Meeting Intelligence Hub
          </h2>
        </div>
        <Link
          href="/agent-chat"
          className="inline-flex items-center gap-1.5 rounded-xl border border-accent/40 bg-accent/10 px-3.5 py-2 text-xs font-semibold text-accent hover:bg-accent/15 transition-all shadow-2xs"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Ask Agent Memory</span>
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-border bg-surface p-5 shadow-xs transition-all hover:border-border/80">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-text-tertiary">Meetings</p>
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10 text-accent border border-accent/20">
              <Calendar className="h-4 w-4" />
            </span>
          </div>
          <p className="mt-3 text-3xl font-bold tracking-tight text-foreground">{metrics.totalMeetings}</p>
          <p className="mt-1 text-xs text-text-secondary">Indexed in workspace memory</p>
        </div>
        <div className="rounded-2xl border border-border bg-surface p-5 shadow-xs transition-all hover:border-border/80">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-text-tertiary">Action Items</p>
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
              <CheckSquare className="h-4 w-4" />
            </span>
          </div>
          <p className="mt-3 text-3xl font-bold tracking-tight text-foreground">{metrics.totalActionItems}</p>
          <p className="mt-1 text-xs text-text-secondary">Extracted & assigned tasks</p>
        </div>
        <div className="rounded-2xl border border-border bg-surface p-5 shadow-xs transition-all hover:border-border/80">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-text-tertiary">Audio Duration</p>
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-sky-500/10 text-sky-500 border border-sky-500/20">
              <Clock className="h-4 w-4" />
            </span>
          </div>
          <p className="mt-3 text-3xl font-bold tracking-tight text-foreground">{metrics.minutes} <span className="text-lg font-normal text-text-tertiary">min</span></p>
          <p className="mt-1 text-xs text-text-secondary">Transcribed & diarized</p>
        </div>
      </div>

      <div>
        <h3 className="heading-title text-foreground">Automation Dispatchers</h3>
        <p className="mt-1 text-xs text-text-secondary">
          Integrated tool connectors for post-meeting actions.
        </p>
      </div>

      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {tools.map((tool) => {
          const ToolIcon = tool.icon;
          return (
            <div key={tool.name} className="flex flex-col justify-between rounded-2xl border border-border bg-surface p-4 shadow-xs transition-all hover:border-border/90 hover:shadow-sm">
              <div>
                <div className="flex items-center gap-2.5 mb-3">
                  <span className={`flex h-8 w-8 items-center justify-center rounded-xl border ${tool.accent}`}>
                    <ToolIcon className="h-4 w-4" />
                  </span>
                  <p className="text-xs font-semibold text-foreground">{tool.name}</p>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">{tool.purpose}</p>
              </div>
              <p className="mt-3 pt-2.5 border-t border-border/50 text-[11px] font-medium text-text-tertiary">{tool.useFor}</p>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between">
        <h3 className="heading-title text-foreground">Recent meetings</h3>
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
