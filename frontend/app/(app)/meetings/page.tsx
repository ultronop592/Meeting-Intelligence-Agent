"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { useUploadMeeting } from "@/lib/hooks/use-upload-meeting";
import { useJobStatus } from "@/lib/hooks/use-job-status";
import { MeetingCard } from "@/components/meeting/meeting-card";
import { UploadDropzone } from "@/components/meeting/upload-dropzone";
import { ProcessingTimeline } from "@/components/meeting/processing-timeline";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { toUserErrorMessage } from "@/lib/api/client";

export default function MeetingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useMeetings();
  const uploadMutation = useUploadMeeting();
  const activeJobIdQuery = useQuery<string | null>({
    queryKey: ["active-job-id"],
    queryFn: async () => null,
    initialData: null,
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const jobStatus = useJobStatus(activeJobIdQuery.data ?? null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "actionable">("all");

  useEffect(() => {
    if (uploadMutation.isSuccess) {
      queryClient.setQueryData(["active-job-id"], uploadMutation.data.job_id);
      toast.success("Upload complete. Processing started.");
    }
    if (uploadMutation.isError) {
      toast.error(toUserErrorMessage(uploadMutation.error));
    }
  }, [uploadMutation.isSuccess, uploadMutation.isError, uploadMutation.error]);

  useEffect(() => {
    if (!jobStatus.data) return;

    if (jobStatus.data.status === "processing") return;

    if (jobStatus.data.status === "completed") {
      toast.success("Meeting processed successfully.");
    } else if (jobStatus.data.status === "completed_with_errors") {
      toast.error("Meeting completed with warnings. Check details in meeting view.");
    } else if (jobStatus.data.status === "failed") {
      const reason = jobStatus.data.errors?.[0] || "Processing failed.";
      toast.error(reason);
    }

    queryClient.setQueryData(["active-job-id"], null);
    void queryClient.invalidateQueries({ queryKey: ["meetings"] });
  }, [jobStatus.data, queryClient]);

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

  const pipelineMessage =
    jobStatus.data?.status === "processing"
      ? "AI agents are processing transcript, extraction, and summary nodes."
      : "Upload a recording to trigger transcription, extraction, summary, and action pipelines.";

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

      <div className="grid gap-4 lg:grid-cols-[1.2fr_2fr]">
        <UploadDropzone
          onUpload={(file, onProgress, signal) =>
            uploadMutation.mutateAsync({ file, onProgress, signal })
          }
          disabled={uploadMutation.isPending}
          maxSizeMb={1024}
        />
        <div className="flex flex-col gap-3 rounded-[16px] border border-border bg-surface p-4">
          <div className="rounded-[12px] border border-border bg-surface-2 px-3 py-2 text-xs text-text-secondary">
            {pipelineMessage}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              placeholder="Search meetings"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="flex rounded-full border border-border bg-surface-2 p-1 text-xs">
              {([
                { key: "all", label: "All" },
                { key: "actionable", label: "Actionable" },
              ] as const).map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`rounded-full px-3 py-1 ${
                    filter === item.key
                      ? "bg-accent text-foreground"
                      : "text-text-secondary"
                  }`}
                  onClick={() => setFilter(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="text-xs text-text-tertiary">
            {filtered.length} meetings shown
          </div>
        </div>
      </div>

      <ProcessingTimeline
        status={jobStatus.data?.status}
        completedNodes={jobStatus.data?.completed_nodes}
        errors={jobStatus.data?.errors}
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

      {jobStatus.data?.status === "processing" ? (
        <div className="rounded-[16px] border border-border bg-surface-2 p-4 text-sm text-text-secondary">
          Processing in progress. We will refresh your meetings when the job is done.
        </div>
      ) : null}

      {jobStatus.data?.status === "failed" ? (
        <div className="rounded-[16px] border border-danger/40 bg-danger/10 p-4 text-sm text-danger">
          Processing failed: {jobStatus.data.errors?.[0] || "Unknown error"}
        </div>
      ) : null}
    </div>
  );
}
