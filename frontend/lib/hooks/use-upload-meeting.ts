"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { meetingApi } from "@/lib/api/meetings";

type UploadMutationInput = {
  file: File;
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
};

export function useUploadMeeting() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ file, onProgress, signal }: UploadMutationInput) => {
      const upload = await meetingApi.uploadAudio(file, onProgress, signal);
      const processResult = await meetingApi.processMeeting({
        audio_file_path: upload.audio_file_path,
        storage_key: upload.storage_key,
        audio_filename: upload.filename,
      });
      return {
        ...processResult,
        filename: upload.filename,
        size_mb: upload.size_mb,
      };
    },
    onSuccess: (data) => {
      if (data?.job_id) {
        queryClient.setQueryData(["active-job-meta"], {
          jobId: data.job_id,
          startedAt: Date.now(),
          lastDurationMs: null,
          fileName: data.filename ?? null,
          fileSizeMb: data.size_mb ?? null,
          isDismissed: false,
        });
        router.push(`/meetings/${data.job_id}`);
      }
    },
  });
}
