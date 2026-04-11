"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMeetingDetail } from "@/lib/hooks/use-meeting-detail";
import { useAgentChat } from "@/lib/hooks/use-agent-chat";
import { meetingApi } from "@/lib/api/meetings";
import { toUserErrorMessage } from "@/lib/api/client";
import { ChatBubble } from "@/components/chat/chat-bubble";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";

export default function MeetingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const meetingId = typeof params?.id === "string" ? params.id : null;
  const { data, isLoading, error, refetch } = useMeetingDetail(meetingId);
  const chatMutation = useAgentChat();
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => meetingApi.deleteMeeting(id),
  });
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<{ role: "user" | "assistant"; message: string }[]>(
    []
  );

  const title = useMemo(() => data?.meeting.title ?? "Meeting detail", [data?.meeting.title]);

  const sendMessage = async () => {
    const content = message.trim();
    if (!content || !meetingId) return;
    setThread((prev) => [...prev, { role: "user", message: content }]);
    setMessage("");

    try {
      const response = await chatMutation.mutateAsync({
        question: content,
        meeting_id: meetingId,
      });
      setThread((prev) => [...prev, { role: "assistant", message: response.answer }]);
    } catch {
      toast.error("Agent is unavailable. Try again shortly.");
    }
  };

  const deleteMeeting = async () => {
    if (!meetingId || deleteMutation.isPending) return;

    const confirmed = window.confirm(
      "Delete this meeting permanently? This will remove summary, action items, decisions, and related records."
    );
    if (!confirmed) return;

    try {
      await deleteMutation.mutateAsync(meetingId);
      toast.success("Meeting deleted successfully.");
      await queryClient.invalidateQueries({ queryKey: ["meetings"] });
      router.push("/meetings");
    } catch (err) {
      toast.error(toUserErrorMessage(err));
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[2.2fr_1fr]">
      <div className="space-y-4">
        <div className="rounded-[16px] border border-border bg-surface p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-text-tertiary">Meeting</p>
              <h2 className="mt-2 text-xl font-semibold text-foreground">{title}</h2>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Refresh
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={!meetingId || deleteMutation.isPending}
                onClick={() => void deleteMeeting()}
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete"}
              </Button>
            </div>
          </div>
          {error ? (
            <p className="mt-3 text-sm text-danger">Unable to load meeting details.</p>
          ) : null}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonLoader key={index} className="h-28" />
            ))}
          </div>
        ) : data ? (
          <div className="space-y-4">
            <div className="rounded-[16px] border border-border bg-surface p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Summary</p>
              <p className="mt-3 text-sm leading-7 text-text-secondary">
                {data.meeting.detailed_summary}
              </p>
            </div>

            <div className="rounded-[16px] border border-border bg-surface p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Action items</p>
              <div className="mt-4 space-y-3">
                {data.action_items.length === 0 ? (
                  <p className="text-sm text-text-secondary">No action items extracted.</p>
                ) : (
                  data.action_items.map((item) => (
                    <div key={item.id} className="rounded-[12px] border border-border bg-surface-2 p-3">
                      <p className="text-sm font-medium text-foreground">{item.description}</p>
                      <p className="mt-1 text-xs text-text-tertiary">
                        Owner: {item.owner} • Due: {item.due_date} • Priority: {item.priority}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-[16px] border border-border bg-surface p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Decisions</p>
              <div className="mt-4 space-y-3">
                {data.decisions.length === 0 ? (
                  <p className="text-sm text-text-secondary">No decisions extracted.</p>
                ) : (
                  data.decisions.map((decision) => (
                    <div key={decision.id} className="rounded-[12px] border border-border bg-surface-2 p-3">
                      <p className="text-sm font-medium text-foreground">{decision.description}</p>
                      <p className="mt-1 text-xs text-text-tertiary">{decision.context}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex h-full flex-col rounded-[18px] border border-border bg-surface p-4">
        <div className="border-b border-border pb-3">
          <p className="text-sm font-semibold text-foreground">Meeting chat</p>
          <p className="text-xs text-text-tertiary">Ask the agent about this meeting.</p>
        </div>
        <div className="flex-1 space-y-3 overflow-auto py-4">
          {thread.length === 0 ? (
            <div className="rounded-[14px] border border-border bg-surface-2 p-4 text-sm text-text-secondary">
              Ask for action items, decisions, or follow-ups.
            </div>
          ) : (
            thread.map((entry, index) => (
              <ChatBubble key={index} role={entry.role} message={entry.message} />
            ))
          )}
          {chatMutation.isPending ? (
            <ChatBubble role="assistant" message="Thinking..." />
          ) : null}
        </div>
        <div className="flex gap-2 border-t border-border pt-3">
          <Input
            placeholder="Ask a question"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void sendMessage();
              }
            }}
          />
          <Button onClick={() => void sendMessage()} disabled={chatMutation.isPending}>
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}
