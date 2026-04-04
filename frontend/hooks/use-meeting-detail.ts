"use client";

import { useCallback, useEffect, useState } from "react";
import type { MeetingDetailResponse } from "@/types/api";
import { meetingApi } from "@/lib/api/meetings";

export function useMeetingDetail(meetingId: string | null) {
  const [data, setData] = useState<MeetingDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!meetingId) {
      setData(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const detail = await meetingApi.getMeetingDetail(meetingId);
      setData(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load meeting details.");
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    data,
    loading,
    error,
    refresh,
    setData,
  };
}
