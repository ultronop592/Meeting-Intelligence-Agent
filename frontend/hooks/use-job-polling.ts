"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MeetingProcessingStatusResponse } from "@/types/api";
import { meetingApi } from "@/lib/api/meetings";

const MAX_RETRIES = 8;
const INITIAL_DELAY_MS = 1200;
const MAX_DELAY_MS = 8000;

export function useJobPolling() {
  const [status, setStatus] = useState<MeetingProcessingStatusResponse | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<number | null>(null);

  const clearActiveTimeout = () => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  };

  const stopPolling = useCallback(() => {
    clearActiveTimeout();
    setIsPolling(false);
  }, []);

  const startPolling = useCallback((jobId: string) => {
    let retries = 0;
    setError(null);
    setIsPolling(true);

    const poll = async () => {
      try {
        const data = await meetingApi.getProcessingStatus(jobId);
        setStatus(data);

        if (data.status === "completed" || data.status === "completed_with_errors" || data.status === "failed") {
          setIsPolling(false);
          return;
        }

        retries = 0;
        timeoutRef.current = window.setTimeout(poll, INITIAL_DELAY_MS);
      } catch (err) {
        retries += 1;

        if (retries > MAX_RETRIES) {
          setError(err instanceof Error ? err.message : "Polling failed.");
          setIsPolling(false);
          return;
        }

        const delay = Math.min(INITIAL_DELAY_MS * 2 ** retries, MAX_DELAY_MS);
        timeoutRef.current = window.setTimeout(poll, delay);
      }
    };

    void poll();
  }, []);

  useEffect(() => clearActiveTimeout, []);

  return {
    status,
    isPolling,
    error,
    startPolling,
    stopPolling,
    setStatus,
  };
}
