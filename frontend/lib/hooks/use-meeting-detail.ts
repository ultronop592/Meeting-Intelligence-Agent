"use client";

import { useQuery } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";

export function useMeetingDetail(meetingId: string | null) {
  return useQuery({
    queryKey: ["meeting", meetingId],
    queryFn: () => meetingApi.getMeetingDetail(meetingId ?? ""),
    enabled: Boolean(meetingId),
  });
}
