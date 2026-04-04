import { z } from "zod";
import type {
  ActionItemRow,
  ActionItemStatus,
  HealthResponse,
  MeetingDetailResponse,
  MeetingListItem,
  MeetingProcessingStatusResponse,
  ParticipantRow,
  ProcessMeetingRequest,
  ProcessMeetingStartResponse,
  SendResult,
  UpdateActionItemRequest,
  UploadResponse,
} from "@/types/api";
import { apiRequest } from "@/lib/api/client";

const processMeetingSchema = z.object({
  audio_file_path: z.string().min(1),
  audio_filename: z.string().min(1),
});

const updateActionItemSchema = z.object({
  status: z.enum(["open", "in_progress", "done"]),
});

export const meetingApi = {
  health: () => apiRequest<HealthResponse>("/health"),

  uploadAudio: async (file: File) => {
    const form = new FormData();
    form.append("file", file);

    return apiRequest<UploadResponse>("/meeting/upload", {
      method: "POST",
      body: form,
    });
  },

  processMeeting: (payload: ProcessMeetingRequest) => {
    processMeetingSchema.parse(payload);

    return apiRequest<ProcessMeetingStartResponse>("/meetings/process", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getProcessingStatus: (jobId: string) =>
    apiRequest<MeetingProcessingStatusResponse>(`/meetings/status/${jobId}`),

  listMeetings: (params?: { limit?: number; offset?: number }) => {
    const limit = params?.limit ?? 20;
    const offset = params?.offset ?? 0;

    return apiRequest<MeetingListItem[]>(`/meetings?limit=${limit}&offset=${offset}`);
  },

  getMeetingDetail: (meetingId: string) =>
    apiRequest<MeetingDetailResponse>(`/meetings/${meetingId}`),

  updateActionItem: (meetingId: string, itemId: string, status: ActionItemStatus) => {
    const payload: UpdateActionItemRequest = { status };
    updateActionItemSchema.parse(payload);

    return apiRequest<ActionItemRow>(`/meetings/${meetingId}/action-items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },

  deleteMeeting: (meetingId: string) =>
    apiRequest<{ deleted: boolean; meeting_id: string }>(`/meetings/${meetingId}`, {
      method: "DELETE",
    }),

  sendEmail: (meetingId: string) =>
    apiRequest<SendResult>(`/meetings/${meetingId}/send/email`, { method: "POST" }),

  sendSlack: (meetingId: string) =>
    apiRequest<SendResult>(`/meetings/${meetingId}/send/slack`, { method: "POST" }),

  sendJira: (meetingId: string) =>
    apiRequest<SendResult>(`/meetings/${meetingId}/send/jira`, { method: "POST" }),

  sendCalendar: (meetingId: string, daysFromNow = 7) =>
    apiRequest<SendResult>(`/meetings/${meetingId}/send/calendar?days_from_now=${daysFromNow}`, {
      method: "POST",
    }),

  updateParticipantEmail: (meetingId: string, participantId: string, email: string) =>
    apiRequest<ParticipantRow>(
      `/meetings/${meetingId}/participants/${participantId}?email=${encodeURIComponent(email)}`,
      {
        method: "PATCH",
      }
    ),
};
