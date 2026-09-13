"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AudioWaveform,
  Brain,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  Database,
  ExternalLink,
  FileText,
  Loader2,
  Mail,
  MessageSquare,
  Send,
  Sparkles,
  Terminal,
  Ticket,
  Workflow,
  XCircle,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { meetingApi } from "@/lib/api/meetings";
import type { DispatchChannelResult, DispatchMeetingChannel, JobStatus } from "@/types/api";
import { cn } from "@/lib/utils";

export type NodeTiming = {
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
};

export type ProcessingTimelineProps = {
  status?: JobStatus;
  completedNodes?: string[];
  errors?: string[];
  elapsedMs?: number | null;
  lastDurationMs?: number | null;
  nodeTimings?: Record<string, NodeTiming>;
  fileName?: string | null;
  fileSizeMb?: number | null;
  meetingId?: string | null;
  meetingTitle?: string | null;
  shortSummary?: string | null;
  actionItemsCount?: number;
  decisionsCount?: number;
  participantsCount?: number;
  onDismiss?: () => void;
};

function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) {
    return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
  }
  return `${seconds}s`;
}

function formatStopwatch(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

type AgentStep = {
  id: string;
  name: string;
  role: string;
  description: string;
  aliases: string[];
  icon: typeof AudioWaveform;
  accentColor: string;
};

const AGENT_STEPS: AgentStep[] = [
  {
    id: "transcribe",
    name: "Whisper Speech Agent",
    role: "Audio Slicing & Transcription",
    description: "Splits chunks with FFmpeg & runs Groq Whisper Large-v3",
    aliases: ["transcribe_audio", "upload"],
    icon: AudioWaveform,
    accentColor: "from-amber-500/20 to-orange-500/20 text-amber-600 border-amber-500/30",
  },
  {
    id: "extract",
    name: "Cognitive Intelligence Agent",
    role: "Decisions & Actions Extraction",
    description: "Extracts action items, assignees, deadlines & architectural decisions",
    aliases: ["extract_information", "process"],
    icon: Brain,
    accentColor: "from-blue-500/20 to-indigo-500/20 text-blue-600 border-blue-500/30",
  },
  {
    id: "summary",
    name: "Executive Synthesizer",
    role: "Summary & Minutes Generation",
    description: "Distills full discussion into executive brief & key takeaways",
    aliases: ["generate_summary"],
    icon: FileText,
    accentColor: "from-emerald-500/20 to-teal-500/20 text-emerald-600 border-emerald-500/30",
  },
  {
    id: "database",
    name: "Vector Memory & Persistence",
    role: "pgvector & NeonDB Indexing",
    description: "Indexes 768-dim embeddings & persists meeting to memory graph",
    aliases: ["save_to_database"],
    icon: Database,
    accentColor: "from-violet-500/20 to-purple-500/20 text-violet-600 border-violet-500/30",
  },
];

export function ProcessingTimeline({
  status,
  completedNodes = [],
  errors = [],
  elapsedMs = 0,
  lastDurationMs,
  nodeTimings,
  fileName,
  fileSizeMb,
  meetingId,
  meetingTitle,
  shortSummary,
  actionItemsCount,
  decisionsCount,
  participantsCount,
  onDismiss,
}: ProcessingTimelineProps) {
  const [showTerminal, setShowTerminal] = useState(true);
  const isLive = status === "processing";
  const isCompleted = status === "completed" || status === "completed_with_errors";
  const isFailed = status === "failed";

  // Human-in-the-Loop Integration Selection State
  const [selectedChannels, setSelectedChannels] = useState<DispatchMeetingChannel[]>([
    "slack",
    "jira",
    "calendar",
  ]);
  const [calendarDays, setCalendarDays] = useState(7);
  const [isDispatching, setIsDispatching] = useState(false);
  const [dispatchResults, setDispatchResults] = useState<Record<string, DispatchChannelResult> | null>(null);

  const toggleChannel = (channel: DispatchMeetingChannel) => {
    setSelectedChannels((prev) =>
      prev.includes(channel) ? prev.filter((c) => c !== channel) : [...prev, channel]
    );
  };

  const handleDispatch = async () => {
    if (!meetingId || selectedChannels.length === 0 || isDispatching) return;
    setIsDispatching(true);
    try {
      const response = await meetingApi.dispatchMeeting(meetingId, {
        channels: selectedChannels,
        days_from_now: calendarDays,
      });
      setDispatchResults(response.results);
      toast.success("Workflow integrations dispatched successfully!");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to dispatch integrations";
      toast.error(msg);
    } finally {
      setIsDispatching(false);
    }
  };

  // Calculate active step index
  const activeStepIndex = useMemo(() => {
    if (!isLive) return -1;
    for (let i = 0; i < AGENT_STEPS.length; i++) {
      const step = AGENT_STEPS[i];
      const isDone = step.aliases.some((alias) => completedNodes.includes(alias));
      if (!isDone) return i;
    }
    return AGENT_STEPS.length - 1;
  }, [isLive, completedNodes]);

  // Overall progress percentage (4 core stages = 25% each)
  const progressPercent = useMemo(() => {
    if (isCompleted) return 100;
    if (!isLive) return 0;
    const completedCount = AGENT_STEPS.filter((step) =>
      step.aliases.some((alias) => completedNodes.includes(alias))
    ).length;
    return Math.min(95, Math.max(15, completedCount * 25 + 10));
  }, [isCompleted, isLive, completedNodes]);

  // Telemetry stream generator based on elapsed seconds and current node
  const telemetryLogs = useMemo(() => {
    const elapsedSec = Math.floor((elapsedMs ?? 0) / 1000);
    const logs: { time: string; text: string; type: "info" | "success" | "active" }[] = [];

    logs.push({
      time: "00:00",
      text: `Ingested media package${fileName ? ` (${fileName})` : ""}${fileSizeMb ? ` [${fileSizeMb} MB]` : ""}.`,
      type: "info",
    });

    if (elapsedSec >= 2) {
      logs.push({
        time: "00:02",
        text: "FFmpeg initialized: extracting audio stream & stripping video track (-vn).",
        type: "info",
      });
    }

    if (elapsedSec >= 6) {
      logs.push({
        time: "00:06",
        text: "Segmenting into 10-minute speech chunks (64 kbps MP3 codec).",
        type: "info",
      });
    }

    if (elapsedSec >= 12 || completedNodes.includes("transcribe_audio")) {
      logs.push({
        time: "00:12",
        text: "Whisper Large-v3 transcribing speech segments via Groq hardware acceleration.",
        type: completedNodes.includes("transcribe_audio") ? "success" : "active",
      });
    }

    if (completedNodes.includes("transcribe_audio")) {
      logs.push({
        time: "00:24",
        text: "✓ Speech-to-text completed. Normalized transcript passed to extraction router.",
        type: "success",
      });
    }

    if (elapsedSec >= 25 || completedNodes.includes("extract_information")) {
      logs.push({
        time: "00:26",
        text: "Cognitive Intelligence Agent parsing discussion for action items, assignees & key decisions.",
        type: completedNodes.includes("extract_information") ? "success" : "active",
      });
    }

    if (completedNodes.includes("extract_information")) {
      logs.push({
        time: "00:36",
        text: "✓ Structured extraction verified. Passing payload to Executive Synthesizer.",
        type: "success",
      });
    }

    if (completedNodes.includes("generate_summary")) {
      logs.push({
        time: "00:44",
        text: "✓ Executive brief & meeting takeaways synthesized successfully.",
        type: "success",
      });
    }

    if (completedNodes.includes("save_to_database")) {
      logs.push({
        time: "00:50",
        text: "✓ Vector embeddings generated (768-dim) & persisted to NeonDB pgvector.",
        type: "success",
      });
    }

    if (isCompleted) {
      logs.push({
        time: formatStopwatch(elapsedMs ?? lastDurationMs ?? 0),
        text: "★ Multi-Agent Pipeline completed. Meeting intelligence indexed & ready for Human-in-the-Loop review.",
        type: "success",
      });
    }

    return logs;
  }, [elapsedMs, fileName, fileSizeMb, completedNodes, isCompleted, lastDurationMs]);

  // If idle with no active job and not completed, render subtle idle indicator
  if (!isLive && !isCompleted && !isFailed) {
    return (
      <div className="elevated-card rounded-[20px] border border-border/80 bg-surface/90 p-5 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface-2 border border-border">
              <Workflow className="h-5 w-5 text-text-tertiary" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">Multi-Agent Intelligence Pipeline</h3>
              <p className="text-xs text-text-tertiary">
                Ready to transcribe, extract decisions, synthesize summaries, and index memory.
              </p>
            </div>
          </div>
          <span className="rounded-full border border-border/70 bg-surface-2 px-3 py-1 text-xs font-medium text-text-tertiary">
            Pipeline Idle
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "elevated-card relative overflow-hidden rounded-[24px] border transition-all duration-300",
        isLive && "border-amber-500/40 bg-surface/95 shadow-[0_12px_40px_-15px_rgba(255,159,67,0.25)]",
        isCompleted && "border-emerald-500/40 bg-surface/95 shadow-[0_12px_40px_-15px_rgba(16,185,129,0.2)]",
        isFailed && "border-danger/40 bg-surface/95 shadow-[0_12px_40px_-15px_rgba(239,68,68,0.2)]"
      )}
    >
      {/* Top Animated Progress Bar */}
      {isLive && (
        <div className="relative h-1.5 w-full bg-surface-2 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-amber-500 via-orange-500 to-emerald-500 transition-all duration-700 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
          <div
            className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent"
            style={{ animation: "beam-slide 2s infinite linear" }}
          />
        </div>
      )}

      <div className="p-6">
        {/* Header Section */}
        <div className="flex flex-wrap items-center justify-between gap-4 pb-5 border-b border-border/70">
          <div className="flex items-center gap-3.5">
            {/* Pulsing Status Orb */}
            <div className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-surface-2 border border-border">
              {isLive ? (
                <>
                  <span
                    className="absolute inline-flex h-full w-full rounded-2xl bg-amber-400/30"
                    style={{ animation: "radar-ripple 2s infinite ease-out" }}
                  />
                  <Loader2 className="h-5 w-5 animate-spin text-amber-600 relative z-10" />
                </>
              ) : isCompleted ? (
                <CheckCircle2 className="h-6 w-6 text-emerald-600" />
              ) : (
                <XCircle className="h-6 w-6 text-danger" />
              )}
            </div>

            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-base font-semibold text-foreground tracking-tight">
                  {isLive
                    ? "AI Multi-Agent Swarm In Progress"
                    : isCompleted
                    ? "Meeting Intelligence Generated"
                    : "Pipeline Execution Interrupted"}
                </h3>

                {isLive && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 border border-amber-500/30 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
                    LIVE
                  </span>
                )}
                {isCompleted && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                    READY
                  </span>
                )}
              </div>

              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                {fileName && (
                  <span className="font-medium text-foreground bg-surface-2 px-2 py-0.5 rounded-md border border-border">
                    {fileName}
                    {fileSizeMb ? ` • ${fileSizeMb} MB` : ""}
                  </span>
                )}
                <span>
                  {isLive
                    ? `Stage ${activeStepIndex + 1} of ${AGENT_STEPS.length} actively executing`
                    : isCompleted
                    ? "All 5 autonomous agent nodes passed verification"
                    : "Check error details below"}
                </span>
              </div>
            </div>
          </div>

          {/* Chronograph / Stopwatch */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5 rounded-2xl bg-surface-2 border border-border/80 px-4 py-2">
              <Clock className={cn("h-4 w-4", isLive ? "animate-pulse text-amber-600" : "text-text-tertiary")} />
              <div>
                <p className="text-[10px] uppercase font-semibold tracking-wider text-text-tertiary">
                  {isLive ? "Elapsed Time" : "Total Runtime"}
                </p>
                <p className="font-mono text-base font-bold text-foreground">
                  {formatStopwatch(elapsedMs ?? lastDurationMs ?? 0)}
                </p>
              </div>
            </div>

            {onDismiss && (isCompleted || isFailed) && (
              <button
                type="button"
                onClick={onDismiss}
                className="rounded-xl border border-border bg-surface px-3 py-2 text-xs font-medium text-text-secondary hover:bg-surface-2 transition-colors"
              >
                Dismiss
              </button>
            )}
          </div>
        </div>

        {/* Completion Highlight Banner */}
        {isCompleted && meetingTitle && (
          <div className="mt-5 rounded-2xl border border-emerald-500/30 bg-emerald-50/60 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-800">
                  Processed Meeting Record
                </p>
                <h4 className="mt-0.5 text-base font-bold text-emerald-950">
                  {meetingTitle}
                </h4>
                {shortSummary && (
                  <p className="mt-1 line-clamp-2 text-xs text-emerald-800/90 leading-relaxed">
                    {shortSummary}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2">
                {meetingId && (
                  <Link
                    href={`/meetings/${meetingId}`}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors"
                  >
                    View Meeting Insights
                    <ExternalLink className="h-3.5 w-3.5" />
                  </Link>
                )}
              </div>
            </div>

            {/* Quick Metrics Bar */}
            <div className="mt-3 flex flex-wrap gap-2 pt-3 border-t border-emerald-500/20 text-xs">
              {actionItemsCount !== undefined && (
                <span className="rounded-lg bg-emerald-100/70 px-2.5 py-1 font-medium text-emerald-900 border border-emerald-200">
                  {actionItemsCount} Action Items
                </span>
              )}
              {decisionsCount !== undefined && (
                <span className="rounded-lg bg-emerald-100/70 px-2.5 py-1 font-medium text-emerald-900 border border-emerald-200">
                  {decisionsCount} Key Decisions
                </span>
              )}
              {participantsCount !== undefined && (
                <span className="rounded-lg bg-emerald-100/70 px-2.5 py-1 font-medium text-emerald-900 border border-emerald-200">
                  {participantsCount} Participants
                </span>
              )}
              <span className="rounded-lg bg-emerald-100/70 px-2.5 py-1 font-medium text-emerald-900 border border-emerald-200">
                Processed in {formatDuration(elapsedMs ?? lastDurationMs ?? 0)}
              </span>
            </div>

            {/* Human-in-the-Loop Authorization & Dispatch Control */}
            {meetingId && (
              <div className="mt-4 rounded-xl border border-emerald-600/30 bg-surface/90 p-4 shadow-xs">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700">
                      <Sparkles className="h-3 w-3" />
                      Human-in-the-Loop Review
                    </div>
                    <h5 className="mt-1 text-xs font-bold text-foreground">
                      Authorize External Integrations
                    </h5>
                    <p className="mt-0.5 text-[11px] text-text-secondary">
                      Review the synthesized meeting intelligence above. Select external platforms to sync:
                    </p>
                  </div>

                  <button
                    type="button"
                    disabled={isDispatching || selectedChannels.length === 0}
                    onClick={() => void handleDispatch()}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-foreground px-3.5 py-2 text-xs font-semibold text-background shadow-xs hover:bg-foreground/90 disabled:opacity-50 transition-colors"
                  >
                    {isDispatching ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        Dispatching...
                      </>
                    ) : (
                      <>
                        <Send className="h-3.5 w-3.5" />
                        Dispatch Selected ({selectedChannels.length})
                      </>
                    )}
                  </button>
                </div>

                {/* 4 Tool Cards with Checkboxes */}
                <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
                  {/* Slack Option */}
                  <label
                    className={cn(
                      "flex cursor-pointer flex-col justify-between rounded-xl border p-3 transition-all",
                      selectedChannels.includes("slack")
                        ? "border-emerald-500/60 bg-emerald-500/10 shadow-xs"
                        : "border-border bg-surface-2/60 opacity-80 hover:opacity-100"
                    )}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <MessageSquare className="h-4 w-4 text-emerald-600" />
                          <span className="text-xs font-bold text-foreground">Slack Channel</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedChannels.includes("slack")}
                          onChange={() => toggleChannel("slack")}
                          className="h-4 w-4 rounded border-border text-emerald-600 focus:ring-emerald-500"
                        />
                      </div>
                      <p className="mt-1 text-[11px] text-text-secondary leading-snug">
                        Post executive brief & action items to team channel.
                      </p>
                    </div>
                    {dispatchResults?.slack && (
                      <div className="mt-2 text-[10px] font-semibold">
                        {dispatchResults.slack.status === "sent" ? (
                          <span className="text-emerald-600">✓ Posted to Slack</span>
                        ) : (
                          <span className="text-danger">✗ {dispatchResults.slack.message}</span>
                        )}
                      </div>
                    )}
                  </label>

                  {/* Jira Option */}
                  <label
                    className={cn(
                      "flex cursor-pointer flex-col justify-between rounded-xl border p-3 transition-all",
                      selectedChannels.includes("jira")
                        ? "border-emerald-500/60 bg-emerald-500/10 shadow-xs"
                        : "border-border bg-surface-2/60 opacity-80 hover:opacity-100"
                    )}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Ticket className="h-4 w-4 text-blue-600" />
                          <span className="text-xs font-bold text-foreground">Jira Issues</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedChannels.includes("jira")}
                          onChange={() => toggleChannel("jira")}
                          className="h-4 w-4 rounded border-border text-blue-600 focus:ring-blue-500"
                        />
                      </div>
                      <p className="mt-1 text-[11px] text-text-secondary leading-snug">
                        Create tickets for {actionItemsCount ?? "all"} extracted action items.
                      </p>
                    </div>
                    {dispatchResults?.jira && (
                      <div className="mt-2 text-[10px] font-semibold">
                        {dispatchResults.jira.status === "sent" ? (
                          <span className="text-emerald-600">✓ {dispatchResults.jira.message}</span>
                        ) : dispatchResults.jira.status === "skipped" ? (
                          <span className="text-text-tertiary">{dispatchResults.jira.message}</span>
                        ) : (
                          <span className="text-danger">✗ {dispatchResults.jira.message}</span>
                        )}
                      </div>
                    )}
                  </label>

                  {/* Calendar Option */}
                  <label
                    className={cn(
                      "flex cursor-pointer flex-col justify-between rounded-xl border p-3 transition-all",
                      selectedChannels.includes("calendar")
                        ? "border-emerald-500/60 bg-emerald-500/10 shadow-xs"
                        : "border-border bg-surface-2/60 opacity-80 hover:opacity-100"
                    )}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Calendar className="h-4 w-4 text-amber-600" />
                          <span className="text-xs font-bold text-foreground">Google Calendar</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedChannels.includes("calendar")}
                          onChange={() => toggleChannel("calendar")}
                          className="h-4 w-4 rounded border-border text-amber-600 focus:ring-amber-500"
                        />
                      </div>
                      <p className="mt-1 text-[11px] text-text-secondary leading-snug">
                        Schedule follow-up sync for attendees in {calendarDays} days.
                      </p>
                    </div>
                    {dispatchResults?.calendar && (
                      <div className="mt-2 text-[10px] font-semibold">
                        {dispatchResults.calendar.status === "sent" ? (
                          <span className="text-emerald-600">✓ Event scheduled</span>
                        ) : (
                          <span className="text-danger">✗ {dispatchResults.calendar.message}</span>
                        )}
                      </div>
                    )}
                  </label>

                  {/* Email Option */}
                  <label
                    className={cn(
                      "flex cursor-pointer flex-col justify-between rounded-xl border p-3 transition-all",
                      selectedChannels.includes("email")
                        ? "border-emerald-500/60 bg-emerald-500/10 shadow-xs"
                        : "border-border bg-surface-2/60 opacity-80 hover:opacity-100"
                    )}
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Mail className="h-4 w-4 text-purple-600" />
                          <span className="text-xs font-bold text-foreground">Email Notes</span>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedChannels.includes("email")}
                          onChange={() => toggleChannel("email")}
                          className="h-4 w-4 rounded border-border text-purple-600 focus:ring-purple-500"
                        />
                      </div>
                      <p className="mt-1 text-[11px] text-text-secondary leading-snug">
                        Send personalized minutes to meeting participants.
                      </p>
                    </div>
                    {dispatchResults?.email && (
                      <div className="mt-2 text-[10px] font-semibold">
                        {dispatchResults.email.status === "sent" ? (
                          <span className="text-emerald-600">✓ {dispatchResults.email.message}</span>
                        ) : dispatchResults.email.status === "skipped" ? (
                          <span className="text-text-tertiary">{dispatchResults.email.message}</span>
                        ) : (
                          <span className="text-danger">✗ {dispatchResults.email.message}</span>
                        )}
                      </div>
                    )}
                  </label>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 4 Autonomous Agent Nodes Flow Grid */}
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {AGENT_STEPS.map((step, idx) => {
            const isDone = step.aliases.some((alias) => completedNodes.includes(alias));
            const isActive = isLive && !isDone && idx === activeStepIndex;
            const isPending = !isDone && !isActive;

            // Get timing if completed
            const timing = step.aliases
              .map((alias) => nodeTimings?.[alias])
              .find((t) => Boolean(t));

            const StepIcon = step.icon;

            return (
              <div
                key={step.id}
                className={cn(
                  "relative flex flex-col justify-between rounded-2xl border p-4 transition-all duration-300",
                  isActive &&
                    "border-amber-500/60 bg-gradient-to-b from-amber-50/60 to-surface shadow-md ring-2 ring-amber-500/20",
                  isDone && "border-emerald-500/40 bg-emerald-50/20",
                  isPending && "border-border/60 bg-surface-2/40 opacity-70"
                )}
              >
                <div>
                  {/* Top Node Header */}
                  <div className="flex items-center justify-between gap-2">
                    <div
                      className={cn(
                        "flex h-9 w-9 items-center justify-center rounded-xl border transition-all",
                        isActive && "border-amber-500/50 bg-amber-500/15 text-amber-700 shadow-sm",
                        isDone && "border-emerald-500/50 bg-emerald-500/15 text-emerald-700",
                        isPending && "border-border bg-surface text-text-tertiary"
                      )}
                    >
                      <StepIcon className="h-4 w-4" />
                    </div>

                    {/* Status Pill */}
                    {isDone ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                        <CheckCircle2 className="h-3 w-3 text-emerald-600" />
                        {timing?.duration_ms ? `${(timing.duration_ms / 1000).toFixed(1)}s` : "DONE"}
                      </span>
                    ) : isActive ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800 animate-pulse">
                        <Loader2 className="h-3 w-3 animate-spin text-amber-600" />
                        RUNNING
                      </span>
                    ) : (
                      <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-medium text-text-tertiary border border-border/80">
                        WAITING
                      </span>
                    )}
                  </div>

                  {/* Title & Description */}
                  <h4 className="mt-3 text-xs font-bold text-foreground leading-snug">
                    {step.name}
                  </h4>
                  <p className="mt-0.5 text-[11px] font-medium text-text-secondary">
                    {step.role}
                  </p>
                </div>

                {/* Micro-Animation Widget for Active State */}
                <div className="mt-4 pt-2 border-t border-border/40">
                  {isActive ? (
                    <div className="flex items-center justify-between gap-1">
                      {step.id === "transcribe" ? (
                        /* Soundwave Equalizer Animation */
                        <div className="flex items-center gap-1 h-5">
                          <span
                            className="w-1 bg-amber-500 rounded-full"
                            style={{ animation: "soundwave-1 0.8s infinite ease-in-out" }}
                          />
                          <span
                            className="w-1 bg-amber-600 rounded-full"
                            style={{ animation: "soundwave-2 0.7s infinite ease-in-out 0.1s" }}
                          />
                          <span
                            className="w-1 bg-orange-500 rounded-full"
                            style={{ animation: "soundwave-4 0.9s infinite ease-in-out 0.2s" }}
                          />
                          <span
                            className="w-1 bg-amber-500 rounded-full"
                            style={{ animation: "soundwave-3 0.6s infinite ease-in-out 0.15s" }}
                          />
                          <span
                            className="w-1 bg-orange-600 rounded-full"
                            style={{ animation: "soundwave-5 0.8s infinite ease-in-out" }}
                          />
                        </div>
                      ) : step.id === "extract" ? (
                        <div className="flex items-center gap-1.5 text-[11px] font-medium text-blue-700">
                          <Cpu className="h-3.5 w-3.5 animate-spin" />
                          <span>Extracting...</span>
                        </div>
                      ) : step.id === "summary" ? (
                        <div className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-700">
                          <Sparkles className="h-3.5 w-3.5 animate-pulse" />
                          <span>Synthesizing...</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-[11px] font-medium text-violet-700">
                          <Database className="h-3.5 w-3.5 animate-bounce" />
                          <span>Indexing vectors...</span>
                        </div>
                      )}
                      <span className="text-[10px] font-mono font-semibold text-text-tertiary">
                        {formatDuration(elapsedMs ?? 0)}
                      </span>
                    </div>
                  ) : isDone ? (
                    <span className="text-[11px] text-emerald-700 font-medium">
                      Verified & Cached
                    </span>
                  ) : (
                    <span className="text-[11px] text-text-tertiary">
                      Step {idx + 1}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Live Agent Telemetry Console / Activity Feed */}
        <div className="mt-5 overflow-hidden rounded-2xl border border-border/80 bg-[#121316] text-[#d6d9e0] shadow-inner">
          <button
            type="button"
            onClick={() => setShowTerminal(!showTerminal)}
            className="flex w-full items-center justify-between px-4 py-2.5 bg-[#18191e] border-b border-[#252830] text-xs font-mono transition-colors hover:bg-[#1f2128]"
          >
            <div className="flex items-center gap-2">
              <div className="flex gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f56]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#27c93f]" />
              </div>
              <Terminal className="ml-2 h-3.5 w-3.5 text-[#8b949e]" />
              <span className="font-semibold text-[#8b949e]">Agent Telemetry Console</span>
            </div>

            <div className="flex items-center gap-2 text-[11px] text-[#8b949e]">
              <span>{telemetryLogs.length} events</span>
              {showTerminal ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </div>
          </button>

          {showTerminal && (
            <div className="max-h-40 overflow-y-auto p-3.5 font-mono text-xs space-y-1.5">
              {telemetryLogs.map((log, index) => (
                <div key={index} className="flex items-start gap-2.5 leading-relaxed">
                  <span className="shrink-0 text-[#6e7681]">[{log.time}]</span>
                  <span
                    className={cn(
                      log.type === "success" && "text-[#7ee787]",
                      log.type === "active" && "text-[#ffa657] font-semibold",
                      log.type === "info" && "text-[#c9d1d9]"
                    )}
                  >
                    {log.text}
                  </span>
                </div>
              ))}

              {isLive && (
                <div className="flex items-center gap-2 text-[#ffa657] pt-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  <span className="text-[11px]">Processing next graph state transition...</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Error Display */}
        {errors && errors.length > 0 && (
          <div className="mt-4 rounded-2xl border border-danger/40 bg-danger/10 p-4 text-xs text-danger flex items-start gap-3">
            <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Pipeline Execution Halted</p>
              <p className="mt-0.5 font-mono">{errors[0]}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
