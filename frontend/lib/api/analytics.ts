import { apiRequest } from "./client";
import type {
  AnalyticsActionItemsResponse,
  AnalyticsParticipantsResponse,
  AnalyticsSummaryResponse,
  AnalyticsTimelineResponse,
  AnalyticsTopicsResponse,
} from "@/types/api";

export async function fetchAnalyticsSummary(): Promise<AnalyticsSummaryResponse> {
  return apiRequest<AnalyticsSummaryResponse>("/analytics/summary");
}

export async function fetchAnalyticsParticipants(): Promise<AnalyticsParticipantsResponse> {
  return apiRequest<AnalyticsParticipantsResponse>("/analytics/participants");
}

export async function fetchAnalyticsTimeline(
  period: "weekly" | "monthly" = "monthly"
): Promise<AnalyticsTimelineResponse> {
  return apiRequest<AnalyticsTimelineResponse>(`/analytics/timeline?period=${period}`);
}

export async function fetchAnalyticsActionItems(): Promise<AnalyticsActionItemsResponse> {
  return apiRequest<AnalyticsActionItemsResponse>("/analytics/action-items");
}

export async function fetchAnalyticsTopics(): Promise<AnalyticsTopicsResponse> {
  return apiRequest<AnalyticsTopicsResponse>("/analytics/topics");
}
