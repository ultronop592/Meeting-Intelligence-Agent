"use client";

import { useMutation } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";

export function useUploadMeeting() {
  return useMutation({
    mutationFn: async (file: File) => {
      const upload = await meetingApi.uploadAudio(file);
      return meetingApi.processMeeting({
        audio_file_path: `${process.env.NEXT_PUBLIC_UPLOAD_DIR_HINT || "/tmp/meeting-agent-uploads"}/${upload.stored_filename}`,
        audio_filename: upload.filename,
      });
    },
  });
}
