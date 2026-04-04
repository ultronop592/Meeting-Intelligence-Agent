"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  CalendarClock,
  CheckCircle2,
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
import { Card, CardContent, CardHeader } from "@/components/ui/card";
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

  return (
    <div className="grid h-screen grid-cols-1 bg-brand-cream-100 md:grid-cols-[300px_1fr] xl:grid-cols-[300px_1fr_360px]">
      <Sidebar
        meetings={meetings}
        loading={meetingsLoading}
        selectedId={selectedMeetingId}
        onSelect={(id) => setSelectedMeetingId(id)}
        onNewMeeting={() => setSelectedMeetingId(null)}
      />

      <main className="flex min-h-0 flex-col bg-brand-cream-50">
        <header className="border-b border-brand-cream-200 bg-brand-cream-50 px-4 py-3 md:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-brand-charcoal-900 md:text-lg">
                {activeTitle}
              </h2>
              <p className="text-xs text-brand-charcoal-700/60">
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
              >
                <MessageSquareDiff className="mr-1 h-4 w-4" /> Email
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void triggerSend("slack")}
              >
                <CheckCircle2 className="mr-1 h-4 w-4" /> Slack
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void triggerSend("jira")}
              >
                Jira
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void triggerSend("calendar")}
              >
                <CalendarClock className="mr-1 h-4 w-4" /> Calendar
              </Button>
              <Button
                variant="danger"
                size="sm"
                disabled={!selectedMeetingId}
                onClick={() => void deleteMeeting()}
              >
                <Trash2 className="mr-1 h-4 w-4" /> Delete
              </Button>
            </div>
          </div>
        </header>

        <section className="flex-1 overflow-auto px-4 py-5 md:px-6">
          {meetingsError ? (
            <Card className="mb-4 border-rose-200 bg-rose-50">
              <CardContent className="text-sm text-rose-700">
                Could not load meetings: {meetingsError}
              </CardContent>
            </Card>
          ) : null}

          {polling.isPolling ? (
            <Card className="mb-4 rounded-2xl">
              <CardHeader>
                <p className="text-sm font-semibold text-brand-charcoal-900">
                  Processing in progress
                </p>
              </CardHeader>
              <CardContent>
                <div className="mb-2 flex items-center gap-2 text-sm text-brand-charcoal-700">
                  <Spinner /> Agent nodes are running. This panel auto-updates
                  using polling with exponential backoff.
                </div>
                <p className="text-xs text-brand-charcoal-700/60">
                  Completed nodes:{" "}
                  {polling.status?.completed_nodes?.join(", ") || "none yet"}
                </p>
              </CardContent>
            </Card>
          ) : null}

          {polling.error ? (
            <Card className="mb-4 border-amber-200 bg-amber-50">
              <CardContent className="text-sm text-amber-700">
                Polling warning: {polling.error}
              </CardContent>
            </Card>
          ) : null}

          {!selectedMeetingId ? (
            <Card className="rounded-2xl border-brand-cream-200 bg-white">
              <CardContent className="space-y-2 py-8">
                <p className="text-base font-medium text-brand-charcoal-900">
                  Start a new intelligence thread
                </p>
                <p className="text-sm leading-6 text-brand-charcoal-700/80">
                  Upload a meeting recording to generate summary, action items,
                  decisions, participants, and downstream notifications.
                </p>
              </CardContent>
            </Card>
          ) : null}

          {selectedMeetingId && detailLoading ? (
            <p className="text-sm text-brand-charcoal-700/60">
              Loading meeting details...
            </p>
          ) : null}
          {selectedMeetingId && detailError ? (
            <p className="text-sm text-rose-600">{detailError}</p>
          ) : null}

          {detail ? (
            <div className="mx-auto max-w-4xl space-y-4">
              <div className="rounded-2xl border border-brand-cream-200 bg-white p-4 shadow-sm">
                <p className="mb-2 text-xs uppercase tracking-[0.12em] text-brand-charcoal-700/60">
                  Assistant
                </p>
                <p className="text-sm leading-7 text-brand-charcoal-700">
                  {detail.meeting.detailed_summary}
                </p>
              </div>

              <Card className="rounded-2xl">
                <CardHeader>
                  <p className="text-sm font-semibold text-brand-charcoal-900">
                    Action items
                  </p>
                </CardHeader>
                <CardContent className="space-y-2">
                  {detail.action_items.length === 0 ? (
                    <p className="text-sm text-brand-charcoal-700/60">
                      No action items.
                    </p>
                  ) : null}
                  {detail.action_items.map((item) => (
                    <div
                      key={item.id}
                      className="rounded-xl border border-brand-cream-200 bg-brand-cream-50 p-3"
                    >
                      <p className="text-sm font-medium text-brand-charcoal-900">
                        {item.description}
                      </p>
                      <p className="text-xs text-brand-charcoal-700/60">
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

              <Card className="rounded-2xl">
                <CardHeader>
                  <p className="text-sm font-semibold text-brand-charcoal-900">
                    Participants
                  </p>
                </CardHeader>
                <CardContent className="space-y-2">
                  {detail.participants.length === 0 ? (
                    <p className="text-sm text-brand-charcoal-700/60">
                      No participants extracted.
                    </p>
                  ) : null}
                  {detail.participants.map((participant) => (
                    <div
                      key={participant.id}
                      className="rounded-xl border border-brand-cream-200 p-3"
                    >
                      <p className="text-sm font-medium text-brand-charcoal-900">
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

      <DetailsPanel detail={detail} />
    </div>
  );
}
