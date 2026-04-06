"use client";

import { useMutation } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api/meetings";
import type { AgentQueryRequest } from "@/types/api";

export function useAgentChat() {
  return useMutation({
    mutationFn: (payload: AgentQueryRequest) => meetingApi.queryAgent(payload),
  });
}
