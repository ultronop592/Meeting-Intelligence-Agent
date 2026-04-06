"use client";

import { useQuery } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";

export function useJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ["job-status", jobId],
    queryFn: () => meetingApi.getProcessingStatus(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: (data) =>
      data && data.status === "processing" ? 2000 : false,
  });
}
