"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";
import type { AgentQueryRequest } from "@/types/api";

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
    onDone?: (sources: string[]) => void
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

