"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";
import type { MeetingProcessingStatusResponse } from "@/types/api";

function getWebSocketUrl(jobId: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  const wsProto = baseUrl.startsWith("https") ? "wss" : "ws";
  const cleanHost = baseUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "");
  return `${wsProto}://${cleanHost}/meetings/ws/${jobId}`;
}

export function useJobStatus(jobId: string | null) {
  const queryClient = useQueryClient();
  const [wsConnected, setWsConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  // TanStack Query handles initial fetch & HTTP fallback polling
  const query = useQuery<MeetingProcessingStatusResponse>({
    queryKey: ["job-status", jobId],
    queryFn: () => meetingApi.getProcessingStatus(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: (q) => {
      // If WebSocket is connected and receiving events, disable polling.
      // If WebSocket is down or disconnected and job is processing, poll every 2s.
      if (wsConnected) return false;
      return q.state.data?.status === "processing" ? 2000 : false;
    },
  });

  useEffect(() => {
    if (!jobId || typeof window === "undefined") return;

    // If job is already completed or failed, do not open WebSocket
    if (query.data?.status === "completed" || query.data?.status === "failed") {
      return;
    }

    let isSubscribed = true;
    const wsUrl = getWebSocketUrl(jobId);
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      if (!isSubscribed) {
        ws.close();
        return;
      }
      setWsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === "ping") {
          ws.send("pong");
          return;
        }

        queryClient.setQueryData<MeetingProcessingStatusResponse>(
          ["job-status", jobId],
          (old) => {
            if (!old) {
              return {
                status: data.status || "processing",
                completed_nodes: data.completed_nodes || [],
                errors: data.errors || [],
                meeting_id: data.meeting_id || null,
                title: data.title,
                short_summary: data.short_summary,
                duration_ms: data.duration_ms,
              };
            }

            const updatedNodes = data.completed_nodes
              ? Array.from(new Set([...old.completed_nodes, ...data.completed_nodes]))
              : old.completed_nodes;

            return {
              ...old,
              ...data,
              completed_nodes: updatedNodes,
              status: data.status || old.status,
              meeting_id: data.meeting_id ?? old.meeting_id,
              title: data.title ?? old.title,
              short_summary: data.short_summary ?? old.short_summary,
              duration_ms: data.duration_ms ?? old.duration_ms,
              errors: data.errors || old.errors,
            };
          }
        );

        // If job reached terminal status, invalidate to ensure fresh state
        if (data.status === "completed" || data.status === "failed") {
          queryClient.invalidateQueries({ queryKey: ["meetings"] });
          ws.close();
        }
      } catch {
        // ignore parse error
      }
    };

    ws.onerror = () => {
      setWsConnected(false);
    };

    ws.onclose = () => {
      setWsConnected(false);
    };

    return () => {
      isSubscribed = false;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [jobId, query.data?.status, queryClient]);

  return {
    ...query,
    isRealtime: wsConnected,
  };
}
