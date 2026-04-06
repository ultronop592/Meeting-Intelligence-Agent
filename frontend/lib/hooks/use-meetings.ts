"use client";

import { useQuery } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";

export function useMeetings() {
  return useQuery({
    queryKey: ["meetings"],
    queryFn: () => meetingApi.listMeetings(),
  });
}
