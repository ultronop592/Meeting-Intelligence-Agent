"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";
import type {
  AgentQueryRequest,
  CreateChatSessionRequest,
} from "@/types/api";

export function useAgentChat() {
  return useMutation({
    mutationFn: (payload: AgentQueryRequest) => meetingApi.queryAgent(payload),
  });
}

export function useAgentChatStream() {
  const [isStreaming, setIsStreaming] = useState(false);

  const streamQuery = async (
    payload: AgentQueryRequest,
    onChunk: (chunk: string) => void,
    onDone?: (sources: string[], sessionId?: string) => void
  ) => {
    setIsStreaming(true);
    try {
      await meetingApi.queryAgentStream(payload, onChunk, onDone);
    } finally {
      setIsStreaming(false);
    }
  };

  return { streamQuery, isStreaming };
}

export function useChatSessions(limit = 50) {
  return useQuery({
    queryKey: ["chat-sessions", limit],
    queryFn: () => meetingApi.listChatSessions(limit),
  });
}

export function useChatSession(sessionId: string | null) {
  return useQuery({
    queryKey: ["chat-session", sessionId],
    queryFn: () => (sessionId ? meetingApi.getChatSession(sessionId) : null),
    enabled: Boolean(sessionId),
  });
}

export function useCreateChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateChatSessionRequest) =>
      meetingApi.createChatSession(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

export function useDeleteChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => meetingApi.deleteChatSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
    },
  });
}

