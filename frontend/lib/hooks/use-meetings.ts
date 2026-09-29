"use client";

import { useQuery } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";

export interface UseMeetingsParams {
  limit?: number;
  offset?: number;
}

export function useMeetings(params?: UseMeetingsParams) {
  const limit = params?.limit ?? 20;
  const offset = params?.offset ?? 0;

  return useQuery({
    queryKey: ["meetings", limit, offset],
    queryFn: () => meetingApi.listMeetings({ limit, offset }),
  });
}
