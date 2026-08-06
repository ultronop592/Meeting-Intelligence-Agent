import { useQuery } from "@tanstack/react-query";
import {
  fetchAnalyticsActionItems,
  fetchAnalyticsParticipants,
  fetchAnalyticsSummary,
  fetchAnalyticsTimeline,
  fetchAnalyticsTopics,
} from "@/lib/api/analytics";

export function useAnalyticsSummary() {
  return useQuery({
    queryKey: ["analytics", "summary"],
    queryFn: fetchAnalyticsSummary,
  });
}

export function useAnalyticsParticipants() {
  return useQuery({
    queryKey: ["analytics", "participants"],
    queryFn: fetchAnalyticsParticipants,
  });
}

export function useAnalyticsTimeline(period: "weekly" | "monthly" = "monthly") {
  return useQuery({
    queryKey: ["analytics", "timeline", period],
    queryFn: () => fetchAnalyticsTimeline(period),
  });
}

export function useAnalyticsActionItems() {
  return useQuery({
    queryKey: ["analytics", "action-items"],
    queryFn: fetchAnalyticsActionItems,
  });
}

export function useAnalyticsTopics() {
  return useQuery({
    queryKey: ["analytics", "topics"],
    queryFn: fetchAnalyticsTopics,
  });
}
