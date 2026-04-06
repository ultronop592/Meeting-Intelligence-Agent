export type ApiErrorShape = {
  detail?: string;
  message?: string;
  path?: string;
  errors?: string[];
  [key: string]: unknown;
};

export type HealthResponse = {
  status: string;
  version: string;
  database?: string;
};

export type UploadResponse = {
  filename: string;
  stored_filename: string;
  size_bytes: number;
  size_mb: number;
};

export type ProcessMeetingRequest = {
  audio_file_path: string;
  audio_filename: string;
};

export type ProcessMeetingStartResponse = {
  job_id: string;
  message: string;
  status: "processing";
};

export type JobStatus = "processing" | "completed" | "completed_with_errors" | "failed";

export type MeetingProcessingStatusResponse = {
  status: JobStatus;
  completed_nodes: string[];
  errors: string[];
  meeting_id: string | null;
  title?: string | null;
  short_summary?: string | null;
  action_items_count?: number;
  decisions_count?: number;
  participants_count?: number;
  jira_tickets_created?: number;
  calendar_event_id?: string | null;
  notifications_sent?: number;
};

export type MeetingListItem = {
  id: string;
  title: string;
  audio_filename: string;
  duration_minutes: number;
  short_summary: string;
  action_items_count: number;
  created_at: string | null;
};

export type ActionItemStatus = "open" | "in_progress" | "done";
export type Priority = "low" | "medium" | "high";

export type MeetingRow = {
  id: string;
  title: string;
  audio_filename: string;
  duration_minutes: number;
  short_summary: string;
  detailed_summary: string;
  embedding_status: "pending" | "completed" | "failed";
  created_at: string | null;
};

export type ActionItemRow = {
  id: string;
  meeting_id: string;
  description: string;
  owner: string;
  due_date: string;
  priority: Priority;
  jira_ticket_id: string | null;
  status: ActionItemStatus;
};

export type DecisionRow = {
  id: string;
  meeting_id: string;
  description: string;
  context: string;
};

export type ParticipantRow = {
  id: string;
  meeting_id: string;
  name: string;
  email: string | null;
};

export type NotificationLogRow = {
  id: string;
  meeting_id: string;
  type: "slack" | "email" | "jira" | "calendar";
  status: "pending" | "sent" | "failed";
  detail: string | null;
  created_at: string | null;
};

export type MeetingDetailResponse = {
  meeting: MeetingRow;
  action_items: ActionItemRow[];
  decisions: DecisionRow[];
  participants: ParticipantRow[];
  notifications: NotificationLogRow[];
};

export type UpdateActionItemRequest = {
  status: ActionItemStatus;
};

export type SendResult = {
  message?: string;
  sent?: number;
  failed?: number;
  created?: string[];
  errors?: string[];
  [key: string]: unknown;
};

export type AgentQueryRequest = {
  question: string;
  meeting_id?: string | null;
};

export type AgentQueryResponse = {
  answer: string;
  sources?: string[];
  [key: string]: unknown;
};
