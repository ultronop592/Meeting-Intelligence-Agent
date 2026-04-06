"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  CalendarClock,
  CheckCircle2,
  Command,
  MessageSquareDiff,
  Trash2,
} from "lucide-react";
import { meetingApi } from "@/lib/api/meetings";
import { toUserErrorMessage } from "@/lib/api/client";
import { useJobPolling } from "@/hooks/use-job-polling";
import { useMeetingDetail } from "@/hooks/use-meeting-detail";
import { useMeetings } from "@/hooks/use-meetings";
import type { ActionItemStatus } from "@/types/api";
import { Sidebar } from "@/components/workspace/sidebar";
import { DetailsPanel } from "@/components/workspace/details-panel";
import { Composer } from "@/components/workspace/composer";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";

export function MeetingWorkspace() {
  const {
    data: meetings,
    loading: meetingsLoading,
    error: meetingsError,
    refresh: refreshMeetings,
  } = useMeetings();
  const [selectedMeetingId, setSelectedMeetingId] = useState<string | null>(
    null,
  );
  const [participantDrafts, setParticipantDrafts] = useState<
    Record<string, string>
  >({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [isQuickSwitcherOpen, setIsQuickSwitcherOpen] = useState(false);
  const [quickQuery, setQuickQuery] = useState("");

  const {
    data: detail,
    loading: detailLoading,
    error: detailError,
    refresh: refreshDetail,
  } = useMeetingDetail(selectedMeetingId);

  const polling = useJobPolling();

  const activeTitle = useMemo(() => {
    if (detail?.meeting.title) {
      return detail.meeting.title;
    }

    return "Meeting intelligence workspace";
  }, [detail?.meeting.title]);

  const filteredMeetings = useMemo(() => {
    const normalized = quickQuery.trim().toLowerCase();
    if (!normalized) {
      return meetings;
    }
    return meetings.filter((meeting) => {
      const title = (meeting.title || "").toLowerCase();
      const summary = (meeting.short_summary || "").toLowerCase();
      return title.includes(normalized) || summary.includes(normalized);
    });
  }, [meetings, quickQuery]);

  const handleUploadAndProcess = async (file: File) => {
    setBusyAction("upload");
    try {
      const upload = await meetingApi.uploadAudio(file);
      const processResult = await meetingApi.processMeeting({
        audio_file_path: `${process.env.NEXT_PUBLIC_UPLOAD_DIR_HINT || "/tmp/meeting-agent-uploads"}/${upload.stored_filename}`,
        audio_filename: upload.filename,
      });

      toast.success("Upload completed. Processing started.");
      polling.startPolling(processResult.job_id);
    } catch (error) {
      toast.error(toUserErrorMessage(error));
    } finally {
      setBusyAction(null);
    }
  };

  const withBusyAction = async (
    actionKey: string,
    callback: () => Promise<void>,
  ) => {
    setBusyAction(actionKey);
    try {
      await callback();
    } catch (error) {
      toast.error(toUserErrorMessage(error));
    } finally {
      setBusyAction(null);
    }
  };

  const handleUpdateActionItem = async (
    itemId: string,
    status: ActionItemStatus,
  ) => {
    if (!selectedMeetingId) {
      return;
    }

    await withBusyAction(`action-item-${itemId}`, async () => {
      await meetingApi.updateActionItem(selectedMeetingId, itemId, status);
      await refreshDetail();
      toast.success("Action item updated.");
    });
  };

  const handleParticipantEmailUpdate = async (participantId: string) => {
    if (!selectedMeetingId) {
      return;
    }

    const value = participantDrafts[participantId]?.trim();
    if (!value) {
      toast.error("Email is required.");
      return;
    }

    await withBusyAction(`participant-${participantId}`, async () => {
      await meetingApi.updateParticipantEmail(
        selectedMeetingId,
        participantId,
        value,
      );
      await refreshDetail();
      toast.success("Participant email updated.");
    });
  };

  const triggerSend = async (
    channel: "email" | "slack" | "jira" | "calendar",
  ) => {
    if (!selectedMeetingId) {
      return;
    }

    await withBusyAction(`send-${channel}`, async () => {
      if (channel === "email") {
        await meetingApi.sendEmail(selectedMeetingId);
      }

      if (channel === "slack") {
        await meetingApi.sendSlack(selectedMeetingId);
      }

      if (channel === "jira") {
        await meetingApi.sendJira(selectedMeetingId);
      }

      if (channel === "calendar") {
        await meetingApi.sendCalendar(selectedMeetingId, 7);
      }

      await refreshDetail();
      toast.success(`Send flow for ${channel} completed.`);
    });
  };

  const deleteMeeting = async () => {
    if (!selectedMeetingId) {
      return;
    }

    await withBusyAction("delete-meeting", async () => {
      await meetingApi.deleteMeeting(selectedMeetingId);
      setSelectedMeetingId(null);
      await refreshMeetings();
      toast.success("Meeting deleted.");
    });
  };

  useEffect(() => {
    if (
      polling.status?.meeting_id &&
      polling.status.status !== "processing" &&
      !selectedMeetingId
    ) {
      setSelectedMeetingId(polling.status.meeting_id);
      void refreshMeetings();
    }
  }, [polling.status, refreshMeetings, selectedMeetingId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setIsQuickSwitcherOpen(true);
      }
      if (event.key === "Escape") {
        setIsQuickSwitcherOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const InlineError = ({
    text,
    onRetry,
  }: {
    text: string;
    onRetry: () => void | Promise<void>;
  }) => (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-[12px] border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      <span>{text}</span>
      <Button variant="outline" size="sm" onClick={() => void onRetry()}>
        Retry
      </Button>
    </div>
  );

  return (
    <div className={`grid h-screen grid-cols-1 bg-background md:grid-cols-[300px_1fr] ${detailsOpen ? "xl:grid-cols-[300px_1fr_360px]" : "xl:grid-cols-[300px_1fr_76px]"}`}>
      <Sidebar
        meetings={meetings}
        loading={meetingsLoading}
        selectedId={selectedMeetingId}
        onSelect={(id) => setSelectedMeetingId(id)}
        onNewMeeting={() => setSelectedMeetingId(null)}
      />

      <main className="flex min-h-0 flex-col bg-background">
        <header className="border-b border-border bg-surface px-4 py-3 md:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-foreground md:text-lg">
                {activeTitle}
              </h2>
              <p className="text-xs text-text-secondary">
                Meeting processing, summaries, action tracking, and delivery
                tools.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void triggerSend("email")}
                aria-label="Send meeting summary by email"
              >
                <MessageSquareDiff className="mr-1 h-4 w-4" /> Email
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void triggerSend("slack")}
                aria-label="Send meeting summary to Slack"
              >
                <CheckCircle2 className="mr-1 h-4 w-4" /> Slack
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void triggerSend("jira")}
                aria-label="Create Jira tickets from meeting"
              >
                Jira
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void triggerSend("calendar")}
                aria-label="Create calendar events from meeting"
              >
                <CalendarClock className="mr-1 h-4 w-4" /> Calendar
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void deleteMeeting()}
                aria-label="Delete selected meeting"
              >
                <Trash2 className="mr-1 h-4 w-4" /> Delete
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsQuickSwitcherOpen(true)}
                aria-label="Open quick switcher"
              >
                <Command className="mr-1 h-4 w-4" /> Quick switcher
              </Button>
            </div>
          </div>
        </header>

        <section className="flex-1 overflow-auto px-4 py-5 md:px-6">
          {meetingsError ? (
            <InlineError
              text={`Could not load meetings: ${meetingsError}`}
              onRetry={refreshMeetings}
            />
          ) : null}

          {polling.isPolling ? (
            <Card className="mb-4">
              <CardContent className="space-y-2">
                <p className="text-sm font-semibold text-foreground">Processing in progress</p>
                <div className="flex items-center gap-2 text-sm text-text-secondary">
                  <Spinner /> Agent nodes are running. This panel auto-updates
                  using polling with exponential backoff.
                </div>
                <p className="text-xs text-text-tertiary">
                  Completed nodes:{" "}
                  {polling.status?.completed_nodes?.join(", ") || "none yet"}
                </p>
              </CardContent>
            </Card>
          ) : null}

          {polling.error ? (
            <InlineError text={`Polling warning: ${polling.error}`} onRetry={() => refreshDetail()} />
          ) : null}

          {!selectedMeetingId ? (
            <Card>
              <CardContent className="space-y-2 py-8">
                <p className="text-base font-medium text-foreground">
                  Start a new intelligence thread
                </p>
                <p className="text-sm leading-6 text-text-secondary">
                  Upload a meeting recording to generate summary, action items,
                  decisions, participants, and downstream notifications.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {selectedMeetingId && detailLoading ? (
            <div className="space-y-3" aria-label="Loading meeting details">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="h-24 animate-pulse rounded-[12px] border border-border bg-surface" />
              ))}
            </div>
          ) : null}
          {selectedMeetingId && detailError ? (
            <InlineError
              text={`Could not load meeting details: ${detailError}`}
              onRetry={refreshDetail}
            />
          ) : null}

          {detail ? (
            <div className="mx-auto max-w-4xl space-y-4">
              <div className="rounded-[12px] border border-border bg-surface p-4">
                <p className="mb-2 text-xs uppercase tracking-[0.12em] text-text-tertiary">
                  Assistant
                </p>
                <p className="text-sm leading-7 text-text-secondary">
                  {detail.meeting.detailed_summary}
                </p>
              </div>

              <Card>
                <CardContent className="space-y-2">
                  <p className="text-sm font-semibold text-foreground">
                    Action items
                  </p>
                  {detail.action_items.length === 0 ? (
                    <p className="text-sm text-text-secondary">
                      No action items.
                    </p>
                  ) : null}
                  {detail.action_items.map((item) => (
                    <div
                      key={item.id}
                      className="rounded-[10px] border border-border bg-surface-2 p-3"
                    >
                      <p className="text-sm font-medium text-foreground">
                        {item.description}
                      </p>
                      <p className="text-xs text-text-secondary">
                        Owner: {item.owner} | Due: {item.due_date}
                      </p>
                      <div className="mt-2 flex gap-2">
                        <Button
                          size="sm"
                          variant={
                            item.status === "open" ? "default" : "outline"
                          }
                          onClick={() =>
                            void handleUpdateActionItem(item.id, "open")
                          }
                          disabled={busyAction === `action-item-${item.id}`}
                        >
                          Open
                        </Button>
                        <Button
                          size="sm"
                          variant={
                            item.status === "in_progress"
                              ? "default"
                              : "outline"
                          }
                          onClick={() =>
                            void handleUpdateActionItem(item.id, "in_progress")
                          }
                          disabled={busyAction === `action-item-${item.id}`}
                        >
                          In progress
                        </Button>
                        <Button
                          size="sm"
                          variant={
                            item.status === "done" ? "default" : "outline"
                          }
                          onClick={() =>
                            void handleUpdateActionItem(item.id, "done")
                          }
                          disabled={busyAction === `action-item-${item.id}`}
                        >
                          Done
                        </Button>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardContent className="space-y-2">
                  <p className="text-sm font-semibold text-foreground">
                    Participants
                  </p>
                  {detail.participants.length === 0 ? (
                    <p className="text-sm text-text-secondary">
                      No participants extracted.
                    </p>
                  ) : null}
                  {detail.participants.map((participant) => (
                    <div
                      key={participant.id}
                      className="rounded-[10px] border border-border bg-surface-2 p-3"
                    >
                      <p className="text-sm font-medium text-foreground">
                        {participant.name}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Input
                          placeholder="participant@company.com"
                          defaultValue={participant.email ?? ""}
                          onChange={(event) =>
                            setParticipantDrafts((prev) => ({
                              ...prev,
                              [participant.id]: event.target.value,
                            }))
                          }
                          className="max-w-xs"
                        />
                        <Button
                          size="sm"
                          onClick={() =>
                            void handleParticipantEmailUpdate(participant.id)
                          }
                          disabled={
                            busyAction === `participant-${participant.id}`
                          }
                        >
                          Save email
                        </Button>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          ) : null}
        </section>

        <Composer
          onUploadAndProcess={handleUploadAndProcess}
          busy={busyAction === "upload"}
        />
      </main>

      <DetailsPanel
        detail={detail}
        isOpen={detailsOpen}
        onToggle={() => setDetailsOpen((prev) => !prev)}
      />

      {isQuickSwitcherOpen ? (
        <div className="fixed inset-0 z-40 flex items-start justify-center bg-black/55 p-4 pt-20" role="dialog" aria-modal="true" aria-label="Quick switcher dialog">
          <div className="w-full max-w-xl rounded-[12px] border border-border bg-surface p-3">
            <Input
              value={quickQuery}
              onChange={(event) => setQuickQuery(event.target.value)}
              placeholder="Search meetings..."
              aria-label="Search meetings"
              autoFocus
            />
            <div className="mt-3 max-h-80 overflow-auto rounded-[10px] border border-border bg-surface-2 p-1">
              {filteredMeetings.length === 0 ? (
                <p className="px-3 py-4 text-sm text-text-secondary">No matching meetings.</p>
              ) : (
                <ul>
                  {filteredMeetings.slice(0, 12).map((meeting) => (
                    <li key={meeting.id}>
                      <button
                        type="button"
                        className="w-full rounded-[10px] px-3 py-2 text-left transition-colors duration-150 hover:bg-surface-3"
                        onClick={() => {
                          setSelectedMeetingId(meeting.id);
                          setIsQuickSwitcherOpen(false);
                        }}
                        aria-label={`Open meeting ${meeting.title || "Untitled meeting"}`}
                      >
                        <p className="text-sm font-medium text-foreground">{meeting.title || "Untitled meeting"}</p>
                        <p className="line-clamp-1 text-xs text-text-secondary">{meeting.short_summary}</p>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="mt-2 flex justify-end">
              <Button variant="ghost" size="sm" onClick={() => setIsQuickSwitcherOpen(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
