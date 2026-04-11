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
  AgentQueryRequest,
  AgentQueryResponse,
} from "@/types/api";
import { apiRequest } from "@/lib/api/client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem("mia_token");
}

async function uploadAudioWithProgress(
  file: File,
  onProgress?: (percent: number) => void,
  signal?: AbortSignal
): Promise<UploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);

    xhr.open("POST", `${API_BASE_URL}/meeting/upload`);
    xhr.withCredentials = true;

    const token = getAuthToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) return;
      const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
      onProgress(percent);
    };

    if (signal) {
      if (signal.aborted) {
        reject(new DOMException("Upload aborted", "AbortError"));
        return;
      }

      signal.addEventListener(
        "abort",
        () => {
          xhr.abort();
          reject(new DOMException("Upload aborted", "AbortError"));
        },
        { once: true }
      );
    }

    xhr.onerror = () => reject(new Error("Upload failed due to network error."));
    xhr.onabort = () => reject(new DOMException("Upload aborted", "AbortError"));

    xhr.onload = () => {
      const raw = xhr.responseText || "";
      let payload: unknown;

      try {
        payload = raw ? (JSON.parse(raw) as unknown) : undefined;
      } catch {
        payload = undefined;
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload as UploadResponse);
        return;
      }

      const detail =
        typeof payload === "object" && payload !== null && "detail" in payload
          ? String((payload as { detail?: string }).detail || "")
          : "";
      reject(new Error(detail || `Upload failed (${xhr.status})`));
    };

    xhr.send(form);
  });
}

const processMeetingSchema = z.object({
  audio_file_path: z.string().min(1),
  audio_filename: z.string().min(1),
});

const updateActionItemSchema = z.object({
  status: z.enum(["open", "in_progress", "done"]),
});

export const meetingApi = {
  health: () => apiRequest<HealthResponse>("/health"),

  uploadAudio: (
    file: File,
    onProgress?: (percent: number) => void,
    signal?: AbortSignal
  ) => uploadAudioWithProgress(file, onProgress, signal),

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

  queryAgent: (payload: AgentQueryRequest) =>
    apiRequest<AgentQueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
