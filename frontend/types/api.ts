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

export type NodeTiming = {
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
};

export type MeetingProcessingStatusResponse = {
  status: JobStatus;
  completed_nodes: string[];
  errors: string[];
  meeting_id: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  node_timings?: Record<string, NodeTiming>;
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
  transcript?: string | null;
  diarized_transcript?: string | null;
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

export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type AgentQueryRequest = {
  question: string;
  meeting_id?: string | null;
  session_id?: string | null;
  history?: ChatMessage[];
};

export type AgentQueryResponse = {
  answer: string;
  sources?: string[];
  session_id?: string | null;
  [key: string]: unknown;
};

export type ChatMessageDetail = {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string | null;
  sources?: string[] | null;
};

export type ChatSessionListItem = {
  id: string;
  title: string;
  meeting_id?: string | null;
  meeting_title?: string | null;
  message_count: number;
  preview?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ChatSessionDetail = {
  id: string;
  title: string;
  meeting_id?: string | null;
  messages: ChatMessageDetail[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type CreateChatSessionRequest = {
  meeting_id?: string | null;
  title?: string | null;
};

export type PeriodStats = {
  meetings_count: number;
  action_items_count: number;
  completed_action_items: number;
  completion_rate: number;
};

export type AnalyticsSummaryResponse = {
  total_meetings: number;
  avg_duration_minutes: number;
  total_action_items: number;
  completed_action_items: number;
  completion_rate: number;
  last_7_days: PeriodStats;
  last_30_days: PeriodStats;
};

export type ParticipantAnalyticsItem = {
  name: string;
  meetings_count: number;
  action_items_count: number;
  completed_action_items: number;
};

export type AnalyticsParticipantsResponse = {
  participants: ParticipantAnalyticsItem[];
};

export type TimelineDataPoint = {
  period: string;
  label: string;
  meetings_count: number;
  action_items_count: number;
  completed_action_items: number;
  avg_duration_minutes: number;
};

export type AnalyticsTimelineResponse = {
  period_type: "weekly" | "monthly";
  timeline: TimelineDataPoint[];
};

export type ActionItemOwnerBreakdown = {
  owner: string;
  open: number;
  in_progress: number;
  done: number;
  overdue: number;
  total: number;
};

export type AnalyticsActionItemsResponse = {
  total_open: number;
  total_in_progress: number;
  total_done: number;
  total_overdue: number;
  by_owner: ActionItemOwnerBreakdown[];
};

export type TopicKeywordItem = {
  topic: string;
  count: number;
};

export type AnalyticsTopicsResponse = {
  topics: TopicKeywordItem[];
};

export type DispatchMeetingChannel = "slack" | "jira" | "calendar" | "email";

export type DispatchMeetingRequest = {
  channels: DispatchMeetingChannel[];
  days_from_now?: number;
};

export type DispatchChannelResult = {
  status: "sent" | "failed" | "skipped";
  message?: string;
  created_count?: number;
  failed_count?: number;
  sent_count?: number;
  event_url?: string | null;
  created?: string[];
};

export type DispatchMeetingResponse = {
  meeting_id: string;
  results: Record<string, DispatchChannelResult>;
};

// =============================================================================
// Integrations & User Tool Credentials
// =============================================================================

export type ToolName = "jira" | "slack" | "email" | "calendar";

export type ToolStatusResponse = {
  tool_name: ToolName;
  connected: boolean;
  is_custom: boolean;
  details: {
    url?: string;
    email?: string;
    project_key?: string;
    has_api_token?: boolean;
    api_token_masked?: string | null;
    channel?: string;
    has_webhook_url?: boolean;
    webhook_url_masked?: string | null;
    sender_email?: string;
    sender_name?: string;
    has_api_key?: boolean;
    api_key_masked?: string | null;
    calendar_id?: string;
    has_credentials_json?: boolean;
    is_system_default?: boolean;
    [key: string]: unknown;
  };
};

export type TestConnectionResponse = {
  success: boolean;
  message: string;
  error?: string | null;
};

export type JiraCredentialPayload = {
  url: string;
  email: string;
  api_token?: string;
  project_key: string;
};

export type SlackCredentialPayload = {
  webhook_url?: string;
  channel?: string;
};

export type EmailCredentialPayload = {
  api_key?: string;
  sender_email: string;
  sender_name?: string;
};

export type CalendarCredentialPayload = {
  calendar_id: string;
  credentials_json?: string;
};

