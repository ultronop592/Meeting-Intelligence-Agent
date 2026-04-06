"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { useMeetings } from "@/lib/hooks/use-meetings";
import { useUploadMeeting } from "@/lib/hooks/use-upload-meeting";
import { useJobStatus } from "@/lib/hooks/use-job-status";
import { MeetingCard } from "@/components/meeting/meeting-card";
import { UploadDropzone } from "@/components/meeting/upload-dropzone";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function MeetingsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useMeetings();
  const uploadMutation = useUploadMeeting();
  const [jobId, setJobId] = useState<string | null>(null);
  const jobStatus = useJobStatus(jobId);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "actionable">("all");

  useEffect(() => {
    if (uploadMutation.isSuccess) {
      setJobId(uploadMutation.data.job_id);
      toast.success("Upload complete. Processing started.");
    }
    if (uploadMutation.isError) {
      toast.error("Upload failed. Please try again.");
    }
  }, [uploadMutation.isSuccess, uploadMutation.isError]);

  useEffect(() => {
    if (!jobStatus.data || jobStatus.data.status === "processing") return;
    toast.success("Meeting processed successfully.");
    setJobId(null);
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-text-tertiary">
            Meetings
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-foreground">
            Capture every decision
          </h2>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.2fr_2fr]">
        <UploadDropzone
          onUpload={(file) => uploadMutation.mutateAsync(file)}
          disabled={uploadMutation.isPending}
        />
        <div className="flex flex-col gap-3 rounded-[16px] border border-border bg-surface p-4">
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
    </div>
  );
}
