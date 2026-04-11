"use client";

import { useMutation } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";

type UploadMutationInput = {
  file: File;
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
};

export function useUploadMeeting() {
  return useMutation({
    mutationFn: async ({ file, onProgress, signal }: UploadMutationInput) => {
      const upload = await meetingApi.uploadAudio(file, onProgress, signal);
      return meetingApi.processMeeting({
        audio_file_path: `${process.env.NEXT_PUBLIC_UPLOAD_DIR_HINT || "/tmp/meeting-agent-uploads"}/${upload.stored_filename}`,
        audio_filename: upload.filename,
      });
    },
  });
}
