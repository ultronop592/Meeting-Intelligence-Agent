"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMeetingDetail } from "@/lib/hooks/use-meeting-detail";
import { useAgentChatStream } from "@/lib/hooks/use-agent-chat";
import { meetingApi } from "@/lib/api/meetings";
import { toUserErrorMessage } from "@/lib/api/client";
import type { ActionItemStatus, NotificationLogRow } from "@/types/api";
import { ChatBubble } from "@/components/chat/chat-bubble";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";
import { AudioPlayer } from "@/components/meeting/audio-player";

type SendChannel = "email" | "slack" | "jira" | "calendar";

export default function MeetingDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const meetingId = typeof params?.id === "string" ? params.id : null;
  const { data, isLoading, error, refetch } = useMeetingDetail(meetingId);
  const { streamQuery, isStreaming } = useAgentChatStream();
  const [message, setMessage] = useState("");
  const [thread, setThread] = useState<{ role: "user" | "assistant"; message: string; isStreaming?: boolean }[]>([]);
  const [daysFromNow, setDaysFromNow] = useState(7);
  const [savingActionItemId, setSavingActionItemId] = useState<string | null>(null);
  const [savingParticipantId, setSavingParticipantId] = useState<string | null>(null);
  const [sendingChannel, setSendingChannel] = useState<SendChannel | null>(null);
  const [participantDrafts, setParticipantDrafts] = useState<Record<string, string>>({});
  const [optimisticNotifications, setOptimisticNotifications] = useState<NotificationLogRow[]>([]);
  const [speakerDrafts, setSpeakerDrafts] = useState<Record<string, string>>({});
  const [savingSpeakerMapping, setSavingSpeakerMapping] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const detectedSpeakers = useMemo(() => {
    const text = data?.meeting.diarized_transcript || "";
    const matches = text.match(/SPEAKER_\d+/g) || [];
    return Array.from(new Set(matches));
  }, [data?.meeting.diarized_transcript]);

  const saveSpeakerMappings = async () => {
    if (!meetingId) return;
    setSavingSpeakerMapping(true);
    try {
      await meetingApi.updateSpeakerMapping(meetingId, speakerDrafts);
      toast.success("Speaker labels resolved & transcript updated.");
      await invalidateMeetingData();
    } catch (err) {
      toast.error(toUserErrorMessage(err));
    } finally {
      setSavingSpeakerMapping(false);
    }
  };

  const title = useMemo(() => data?.meeting.title ?? "Meeting detail", [data?.meeting.title]);
  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<string>;
      setSearchQuery((custom.detail || "").trim().toLowerCase());
    };

    window.addEventListener("mia-global-search", handler as EventListener);
    return () => {
      window.removeEventListener("mia-global-search", handler as EventListener);
    };
  }, []);

  const filteredActionItems = useMemo(() => {
    const items = data?.action_items ?? [];
    if (!searchQuery) return items;
    return items.filter((item) =>
      [item.description, item.owner, item.due_date, item.priority, item.status]
        .join(" ")
        .toLowerCase()
        .includes(searchQuery)
    );
  }, [data?.action_items, searchQuery]);

  const filteredDecisions = useMemo(() => {
    const decisions = data?.decisions ?? [];
    if (!searchQuery) return decisions;
    return decisions.filter((decision) =>
      [decision.description, decision.context].join(" ").toLowerCase().includes(searchQuery)
    );
  }, [data?.decisions, searchQuery]);

  const filteredParticipants = useMemo(() => {
    const participants = data?.participants ?? [];
    if (!searchQuery) return participants;
    return participants.filter((participant) =>
      [participant.name, participant.email || ""].join(" ").toLowerCase().includes(searchQuery)
    );
  }, [data?.participants, searchQuery]);

  const allNotifications = useMemo(() => {
    return [...optimisticNotifications, ...(data?.notifications ?? [])];
  }, [optimisticNotifications, data?.notifications]);

  const channelStatuses = useMemo(() => {
    const channels: SendChannel[] = ["email", "slack", "jira", "calendar"];
    return channels.map((channel) => {
      const latest = allNotifications.find((log) => log.type === channel);
      return { channel, status: latest?.status || "idle" };
    });
  }, [allNotifications]);

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => meetingApi.deleteMeeting(id),
  });

  const updateActionItemMutation = useMutation({
    mutationFn: async ({ itemId, status }: { itemId: string; status: ActionItemStatus }) =>
      meetingApi.updateActionItem(meetingId ?? "", itemId, status),
  });

  const updateParticipantMutation = useMutation({
    mutationFn: async ({ participantId, email }: { participantId: string; email: string }) =>
      meetingApi.updateParticipantEmail(meetingId ?? "", participantId, email),
  });

  const sendMessage = async () => {
    const content = message.trim();
    if (!content || !meetingId || isStreaming) return;

    setThread((prev) => [
      ...prev,
      { role: "user", message: content },
      { role: "assistant", message: "", isStreaming: true },
    ]);
    setMessage("");

    try {
      await streamQuery(
        { question: content, meeting_id: meetingId },
        (chunk) => {
          setThread((prev) => {
            const updated = [...prev];
            const lastIndex = updated.length - 1;
            if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
              updated[lastIndex] = {
                ...updated[lastIndex],
                message: updated[lastIndex].message + chunk,
              };
            }
            return updated;
          });
        },
        () => {
          setThread((prev) => {
            const updated = [...prev];
            const lastIndex = updated.length - 1;
            if (lastIndex >= 0 && updated[lastIndex].role === "assistant") {
              updated[lastIndex] = {
                ...updated[lastIndex],
                isStreaming: false,
              };
            }
            return updated;
          });
        }
      );
    } catch {
      toast.error("Agent is unavailable. Try again shortly.");
      setThread((prev) => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        if (lastIndex >= 0 && updated[lastIndex].role === "assistant" && !updated[lastIndex].message) {
          updated[lastIndex] = {
            role: "assistant",
            message: "Sorry, I couldn't process your request right now.",
            isStreaming: false,
          };
        } else if (lastIndex >= 0) {
          updated[lastIndex].isStreaming = false;
        }
        return updated;
      });
    }
  };

  const invalidateMeetingData = async () => {
    await queryClient.invalidateQueries({ queryKey: ["meeting", meetingId] });
    await queryClient.invalidateQueries({ queryKey: ["meetings"] });
  };

  const updateActionStatus = async (itemId: string, status: ActionItemStatus) => {
    if (!meetingId) return;
    setSavingActionItemId(itemId);
    try {
      await updateActionItemMutation.mutateAsync({ itemId, status });
      toast.success("Action item status updated.");
      await invalidateMeetingData();
    } catch (err) {
      toast.error(toUserErrorMessage(err));
    } finally {
      setSavingActionItemId(null);
    }
  };

  const saveParticipantEmail = async (participantId: string) => {
    if (!meetingId) return;
    const email = (participantDrafts[participantId] || "").trim();
    if (!email) {
      toast.error("Please enter an email before saving.");
      return;
    }

    setSavingParticipantId(participantId);
    try {
      await updateParticipantMutation.mutateAsync({ participantId, email });
      toast.success("Participant email updated.");
      await invalidateMeetingData();
    } catch (err) {
      toast.error(toUserErrorMessage(err));
    } finally {
      setSavingParticipantId(null);
    }
  };

  const sendIntegration = async (channel: SendChannel) => {
    if (!meetingId) return;
    setSendingChannel(channel);
    const optimisticId = `optimistic-${channel}-${Date.now()}`;
    setOptimisticNotifications((prev) => [
      {
        id: optimisticId,
        meeting_id: meetingId,
        type: channel,
        status: "pending",
        detail: "Sending...",
        created_at: new Date().toISOString(),
      },
      ...prev,
    ]);

    try {
      if (channel === "email") {
        await meetingApi.sendEmail(meetingId);
      } else if (channel === "slack") {
        await meetingApi.sendSlack(meetingId);
      } else if (channel === "jira") {
        await meetingApi.sendJira(meetingId);
      } else {
        await meetingApi.sendCalendar(meetingId, daysFromNow);
      }

      toast.success(`${channel.toUpperCase()} action sent.`);
      setOptimisticNotifications((prev) =>
        prev.map((entry) =>
          entry.id === optimisticId
            ? { ...entry, status: "sent", detail: "Queued successfully" }
            : entry
        )
      );
      await invalidateMeetingData();
      window.setTimeout(() => {
        setOptimisticNotifications((prev) => prev.filter((entry) => entry.id !== optimisticId));
      }, 2000);
    } catch (err) {
      toast.error(toUserErrorMessage(err));
      setOptimisticNotifications((prev) =>
        prev.map((entry) =>
          entry.id === optimisticId
            ? { ...entry, status: "failed", detail: toUserErrorMessage(err) }
            : entry
        )
      );
    } finally {
      setSendingChannel(null);
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
    <div className="grid gap-6 lg:grid-cols-[2.15fr_1fr]">
      <div className="space-y-4">
        <div className="rounded-[16px] border border-border bg-surface p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
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
          {error ? <p className="mt-3 text-sm text-danger">Unable to load meeting details.</p> : null}
        </div>

        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonLoader key={index} className="h-28" />
            ))}
          </div>
        ) : data ? (
          <div className="space-y-4">
            <AudioPlayer
              audioUrl={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/meetings/${meetingId}/audio`}
              diarizedTranscript={data.meeting.diarized_transcript}
              plainTranscript={data.meeting.transcript}
            />

            <div className="rounded-[16px] border border-border bg-surface p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Summary</p>
              <p className="mt-3 text-sm leading-7 text-text-secondary">{data.meeting.detailed_summary}</p>
              {searchQuery ? (
                <p className="mt-2 text-xs text-text-tertiary">Filter applied: &quot;{searchQuery}&quot;</p>
              ) : null}
            </div>

            <div className="rounded-[16px] border border-border bg-surface p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Action items</p>
                <p className="text-xs text-text-tertiary">PATCH /meetings/:id/action-items/:item_id</p>
              </div>
              <div className="mt-4 space-y-3">
                {filteredActionItems.length === 0 ? (
                  <p className="text-sm text-text-secondary">No action items extracted.</p>
                ) : (
                  filteredActionItems.map((item) => (
                    <div key={item.id} className="rounded-[12px] border border-border bg-surface-2 p-3">
                      <p className="text-sm font-medium text-foreground">{item.description}</p>
                      <p className="mt-1 text-xs text-text-tertiary">
                        Owner: {item.owner} | Due: {item.due_date} | Priority: {item.priority}
                      </p>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <select
                          className="h-8 rounded-[10px] border border-border bg-surface px-2 text-xs"
                          value={item.status}
                          onChange={(event) =>
                            void updateActionStatus(item.id, event.target.value as ActionItemStatus)
                          }
                          disabled={savingActionItemId === item.id}
                        >
                          <option value="open">Open</option>
                          <option value="in_progress">In progress</option>
                          <option value="done">Done</option>
                        </select>
                        {savingActionItemId === item.id ? (
                          <span className="text-xs text-text-tertiary">Saving...</span>
                        ) : null}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-[16px] border border-border bg-surface p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Decisions</p>
              <div className="mt-4 space-y-3">
                {filteredDecisions.length === 0 ? (
                  <p className="text-sm text-text-secondary">No decisions extracted.</p>
                ) : (
                  filteredDecisions.map((decision) => (
                    <div key={decision.id} className="rounded-[12px] border border-border bg-surface-2 p-3">
                      <p className="text-sm font-medium text-foreground">{decision.description}</p>
                      <p className="mt-1 text-xs text-text-tertiary">{decision.context}</p>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-[16px] border border-border bg-surface p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Participants</p>
                <p className="text-xs text-text-tertiary">PATCH /meetings/:id/participants/:participant_id</p>
              </div>
              <div className="mt-4 space-y-3">
                {filteredParticipants.length === 0 ? (
                  <p className="text-sm text-text-secondary">No participants extracted.</p>
                ) : (
                  filteredParticipants.map((participant) => (
                    <div key={participant.id} className="rounded-[12px] border border-border bg-surface-2 p-3">
                      <p className="text-sm font-medium text-foreground">{participant.name}</p>
                      <div className="mt-2 flex gap-2">
                        <Input
                          value={
                            participantDrafts[participant.id] ?? participant.email ?? ""
                          }
                          onChange={(event) =>
                            setParticipantDrafts((prev) => ({
                              ...prev,
                              [participant.id]: event.target.value,
                            }))
                          }
                          placeholder="name@company.com"
                        />
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={savingParticipantId === participant.id}
                          onClick={() => void saveParticipantEmail(participant.id)}
                        >
                          {savingParticipantId === participant.id ? "Saving..." : "Save"}
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Speaker Identity Resolution */}
            <div className="rounded-[16px] border border-border bg-surface p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Speaker Identity Resolution</p>
                  <p className="mt-1 text-xs text-text-secondary">
                    Resolve raw diarization labels (e.g. SPEAKER_00) to actual participant names.
                  </p>
                </div>
                {detectedSpeakers.length > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={savingSpeakerMapping}
                    onClick={() => void saveSpeakerMappings()}
                  >
                    {savingSpeakerMapping ? "Updating..." : "Save Mappings"}
                  </Button>
                )}
              </div>
              <div className="mt-4 space-y-3">
                {detectedSpeakers.length === 0 ? (
                  <p className="text-sm text-text-secondary">
                    No unresolved speaker labels found in diarized transcript.
                  </p>
                ) : (
                  detectedSpeakers.map((spkKey) => (
                    <div key={spkKey} className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-border bg-surface-2 p-3">
                      <span className="font-mono text-xs font-semibold text-accent">{spkKey}</span>
                      <div className="flex flex-1 items-center gap-2 max-w-xs">
                        <Input
                          value={speakerDrafts[spkKey] ?? ""}
                          onChange={(e) =>
                            setSpeakerDrafts((prev) => ({
                              ...prev,
                              [spkKey]: e.target.value,
                            }))
                          }
                          placeholder="e.g. Alice Chen"
                          className="h-8 text-xs bg-surface"
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-[16px] border border-border bg-surface p-5">
              <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Integrations</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {channelStatuses.map((entry) => (
                  <span
                    key={entry.channel}
                    className={`rounded-full border px-2 py-1 text-[11px] uppercase tracking-[0.08em] ${
                      entry.status === "sent"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : entry.status === "failed"
                        ? "border-red-200 bg-red-50 text-red-700"
                        : entry.status === "pending"
                        ? "border-amber-200 bg-amber-50 text-amber-700"
                        : "border-border bg-surface-2 text-text-tertiary"
                    }`}
                  >
                    {entry.channel}: {entry.status}
                  </span>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={sendingChannel !== null}
                  onClick={() => void sendIntegration("email")}
                >
                  {sendingChannel === "email" ? "Sending..." : "Send Email"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={sendingChannel !== null}
                  onClick={() => void sendIntegration("slack")}
                >
                  {sendingChannel === "slack" ? "Sending..." : "Send Slack"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={sendingChannel !== null}
                  onClick={() => void sendIntegration("jira")}
                >
                  {sendingChannel === "jira" ? "Sending..." : "Create Jira"}
                </Button>
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    className="w-28"
                    min={1}
                    max={365}
                    value={daysFromNow}
                    onChange={(event) => setDaysFromNow(Number(event.target.value || 7))}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={sendingChannel !== null}
                    onClick={() => void sendIntegration("calendar")}
                  >
                    {sendingChannel === "calendar" ? "Sending..." : "Book Calendar"}
                  </Button>
                </div>
              </div>

              <div className="mt-4 space-y-2">
                {allNotifications.length === 0 ? (
                  <p className="text-xs text-text-tertiary">No integration logs yet.</p>
                ) : (
                  allNotifications.slice(0, 8).map((log) => (
                    <div key={log.id} className="rounded-[10px] border border-border bg-surface-2 px-3 py-2 text-xs">
                      <span className="font-medium uppercase text-foreground">{log.type}</span>
                      <span className="mx-2 text-text-tertiary">{log.status}</span>
                      <span className="text-text-secondary">{log.detail || "-"}</span>
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
              Ask for action items, decisions, owners, and follow-ups.
            </div>
          ) : (
            thread.map((entry, index) => (
              <ChatBubble
                key={index}
                role={entry.role}
                message={entry.message}
                isStreaming={entry.isStreaming}
              />
            ))
          )}
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
            disabled={isStreaming}
          />
          <Button onClick={() => void sendMessage()} disabled={isStreaming || !message.trim()}>
            {isStreaming ? "Thinking..." : "Send"}
          </Button>
        </div>
      </div>
    </div>
  );
}
