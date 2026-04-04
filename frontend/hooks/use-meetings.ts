"use client";

import { useCallback, useEffect, useState } from "react";
import type { MeetingListItem } from "@/types/api";
import { meetingApi } from "@/lib/api/meetings";

export function useMeetings() {
  const [data, setData] = useState<MeetingListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const rows = await meetingApi.listMeetings();
      setData(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load meetings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    data,
    loading,
    error,
    refresh,
  };
}
