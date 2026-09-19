"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { useUploadMeeting } from "@/lib/hooks/use-upload-meeting";
import { useJobStatus } from "@/lib/hooks/use-job-status";
import { MeetingCard } from "@/components/meeting/meeting-card";
import { UploadDropzone } from "@/components/meeting/upload-dropzone";
import { LiveAudioRecorder } from "@/components/meeting/live-audio-recorder";
import { ProcessingTimeline } from "@/components/meeting/processing-timeline";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { toUserErrorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { Mic, UploadCloud } from "lucide-react";

type JobTimerMeta = {
  jobId: string | null;
  startedAt: number | null;
  lastDurationMs: number | null;
  fileName?: string | null;
  fileSizeMb?: number | null;
  isDismissed?: boolean;
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

export default function MeetingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useMeetings();
  const uploadMutation = useUploadMeeting();
  const activeJobMetaQuery = useQuery<JobTimerMeta>({
    queryKey: ["active-job-meta"],
    queryFn: async () => ({
      jobId: null,
      startedAt: null,
      lastDurationMs: null,
      fileName: null,
      fileSizeMb: null,
      isDismissed: false,
    }),
    initialData: {
      jobId: null,
      startedAt: null,
      lastDurationMs: null,
      fileName: null,
      fileSizeMb: null,
      isDismissed: false,
    },
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const jobStatus = useJobStatus(activeJobMetaQuery.data.jobId);
  const [nowMs, setNowMs] = useState<number | null>(null);
  const [query, setQuery] = useState(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("mia_global_search") || "";
  });
  const [filter, setFilter] = useState<"all" | "actionable">("all");
  const [captureMode, setCaptureMode] = useState<"upload" | "record">("upload");

  useEffect(() => {
    if (jobStatus.data?.status !== "processing") return;
    const id = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => window.clearInterval(id);
  }, [jobStatus.data?.status]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<string>;
      setQuery(custom.detail || "");
    };

    window.addEventListener("mia-global-search", handler as EventListener);
    return () => {
      window.removeEventListener("mia-global-search", handler as EventListener);
    };
  }, []);

  useEffect(() => {
    if (uploadMutation.isSuccess) {
      queryClient.setQueryData<JobTimerMeta>(["active-job-meta"], (prev) => ({
        jobId: uploadMutation.data.job_id,
        startedAt: Date.now(),
        lastDurationMs: prev?.lastDurationMs ?? null,
        fileName: uploadMutation.data.filename ?? null,
        fileSizeMb: uploadMutation.data.size_mb ?? null,
        isDismissed: false,
      }));
      toast.success("Upload complete. Multi-agent processing started.");
    }
    if (uploadMutation.isError) {
      toast.error(toUserErrorMessage(uploadMutation.error));
    }
  }, [
    uploadMutation.isSuccess,
    uploadMutation.isError,
    uploadMutation.error,
    uploadMutation.data?.job_id,
    uploadMutation.data?.filename,
    uploadMutation.data?.size_mb,
    queryClient,
  ]);

  useEffect(() => {
    if (!jobStatus.data) return;

    const startedAt = activeJobMetaQuery.data.startedAt;
    const durationMs = startedAt ? Date.now() - startedAt : null;

    if (jobStatus.data.status === "processing") return;

    if (jobStatus.data.status === "completed") {
      toast.success("Meeting processed successfully!");
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
    } else if (jobStatus.data.status === "completed_with_errors") {
      toast.error("Meeting completed with warnings. Check details in meeting view.");
      void queryClient.invalidateQueries({ queryKey: ["meetings"] });
    } else if (jobStatus.data.status === "failed") {
      const reason = jobStatus.data.errors?.[0] || "Processing failed.";
      toast.error(reason);
    }

    // Retain duration but don't instantly nullify jobId to allow viewing results
    queryClient.setQueryData<JobTimerMeta>(["active-job-meta"], (prev) => ({
      jobId: prev?.jobId ?? null,
      startedAt: prev?.startedAt ?? null,
      lastDurationMs: durationMs ?? prev?.lastDurationMs ?? null,
      fileName: prev?.fileName ?? null,
      fileSizeMb: prev?.fileSizeMb ?? null,
      isDismissed: prev?.isDismissed ?? false,
    }));
  }, [jobStatus.data, activeJobMetaQuery.data.startedAt, queryClient]);

  const handleDismissJob = () => {
    queryClient.setQueryData<JobTimerMeta>(["active-job-meta"], (prev) => ({
      jobId: null,
      startedAt: null,
      lastDurationMs: prev?.lastDurationMs ?? null,
      fileName: prev?.fileName ?? null,
      fileSizeMb: prev?.fileSizeMb ?? null,
      isDismissed: true,
    }));
  };

  const elapsedMs = useMemo(() => {
    const startedAt = activeJobMetaQuery.data.startedAt;
    if (!startedAt || jobStatus.data?.status !== "processing" || nowMs === null) return null;
    return nowMs - startedAt;
  }, [activeJobMetaQuery.data.startedAt, jobStatus.data?.status, nowMs]);

  const filtered = useMemo(() => {
    const meetings = data ?? [];
    const normalized = query.trim().toLowerCase();
    return meetings.filter((meeting) => {
      const matchQuery =
        !normalized ||
        meeting.title.toLowerCase().includes(normalized) ||
        meeting.short_summary.toLowerCase().includes(normalized);
      const matchFilter =
        filter === "all" || meeting.action_items_count > 0;
      return matchQuery && matchFilter;
    });
  }, [data, query, filter]);

  const dashboardStats = useMemo(() => {
    const meetings = data ?? [];
    const actionableMeetings = meetings.filter(
      (meeting) => meeting.action_items_count > 0
    ).length;

    return {
      totalMeetings: meetings.length,
      actionableMeetings,
      activeJobs: jobStatus.data?.status === "processing" ? 1 : 0,
    };
  }, [data, jobStatus.data]);

  return (
    <div className="space-y-app-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-text-tertiary">
            Meetings
          </p>
          <h2 className="heading-title mt-2 text-foreground">
            Capture every decision
          </h2>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <CardContent className="space-y-1 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Total meetings</p>
            <p className="text-2xl font-semibold text-foreground">{dashboardStats.totalMeetings}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Actionable</p>
            <p className="text-2xl font-semibold text-foreground">{dashboardStats.actionableMeetings}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Active jobs</p>
            <p className="text-2xl font-semibold text-foreground">{dashboardStats.activeJobs}</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-2 border-b border-border/60 pb-3">
        <button
          id="tab-upload-audio"
          type="button"
          onClick={() => setCaptureMode("upload")}
          className={cn(
            "inline-flex items-center gap-2 rounded-xl px-3.5 py-1.5 text-xs font-semibold transition-all",
            captureMode === "upload"
              ? "bg-accent text-white shadow-xs"
              : "border border-border bg-surface text-text-secondary hover:text-foreground"
          )}
        >
          <UploadCloud className="h-3.5 w-3.5" />
          Upload Audio File
        </button>
        <button
          id="tab-record-live"
          type="button"
          onClick={() => setCaptureMode("record")}
          className={cn(
            "inline-flex items-center gap-2 rounded-xl px-3.5 py-1.5 text-xs font-semibold transition-all",
            captureMode === "record"
              ? "bg-red-600 text-white shadow-xs"
              : "border border-border bg-surface text-text-secondary hover:text-foreground"
          )}
        >
          <Mic className="h-3.5 w-3.5" />
          Record Meeting Live
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_2fr]">
        {captureMode === "upload" ? (
          <UploadDropzone
            onUpload={(file, onProgress, signal) =>
              uploadMutation.mutateAsync({ file, onProgress, signal })
            }
            disabled={uploadMutation.isPending}
            maxSizeMb={1024}
          />
        ) : (
          <LiveAudioRecorder
            onRecordingComplete={(file) =>
              uploadMutation.mutate({ file })
            }
            disabled={uploadMutation.isPending}
          />
        )}
        <div className="flex flex-col justify-between gap-3 rounded-[16px] border border-border bg-surface p-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-text-tertiary">
              Workspace Search & Filters
            </p>
            <p className="text-xs text-text-secondary mt-0.5">
              Search by title, executive summary, or filter actionable meetings.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              placeholder="Search meetings..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="flex-1 min-w-[200px]"
            />
            <div className="flex rounded-full border border-border bg-surface-2 p-1 text-xs">
              {([
                { key: "all", label: "All" },
                { key: "actionable", label: "Actionable" },
              ] as const).map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`rounded-full px-3 py-1 font-medium transition-colors ${
                    filter === item.key
                      ? "bg-accent text-foreground shadow-xs"
                      : "text-text-secondary hover:text-foreground"
                  }`}
                  onClick={() => setFilter(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="text-xs text-text-tertiary">
            {filtered.length} of {data?.length || 0} meetings shown
          </div>
        </div>
      </div>

      {/* Dedicated Multi-Agent Processing Command Center */}
      <ProcessingTimeline
        status={activeJobMetaQuery.data.isDismissed ? undefined : jobStatus.data?.status}
        completedNodes={jobStatus.data?.completed_nodes}
        errors={jobStatus.data?.errors}
        elapsedMs={elapsedMs}
        lastDurationMs={activeJobMetaQuery.data.lastDurationMs}
        nodeTimings={jobStatus.data?.node_timings}
        fileName={activeJobMetaQuery.data.fileName}
        fileSizeMb={activeJobMetaQuery.data.fileSizeMb}
        meetingId={jobStatus.data?.meeting_id}
        meetingTitle={jobStatus.data?.title}
        shortSummary={jobStatus.data?.short_summary}
        actionItemsCount={jobStatus.data?.action_items_count}
        decisionsCount={jobStatus.data?.decisions_count}
        participantsCount={jobStatus.data?.participants_count}
        onDismiss={handleDismissJob}
      />

      {error ? (
        <div className="rounded-[16px] border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
          We could not load meetings. Please retry.
        </div>
      ) : null}

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <SkeletonLoader key={index} className="h-40" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-[16px] border border-border bg-surface p-6 text-center">
          <p className="text-base font-semibold text-foreground">No meetings yet</p>
          <p className="mt-2 text-sm text-text-secondary">
            Upload your first meeting to generate summaries, action items, and decisions.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((meeting) => (
            <MeetingCard key={meeting.id} meeting={meeting} />
          ))}
        </div>
      )}
    </div>
  );
}
