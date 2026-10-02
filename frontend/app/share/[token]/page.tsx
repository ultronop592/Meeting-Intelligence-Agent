"use client";

import { useEffect, useState, use } from "react";
import {
  Calendar,
  Clock,
  CheckCircle2,
  ListTodo,
  Users,
  FileText,
  AlertTriangle,
  Globe,
  Sparkles,
  Bot,
  ExternalLink,
} from "lucide-react";
import Link from "next/link";
import { AudioPlayer } from "@/components/meeting/audio-player";
import { SkeletonLoader } from "@/components/ui/skeleton-loader";
import { meetingApi } from "@/lib/api/meetings";
import type { PublicMeetingResponse } from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

interface SharePageProps {
  params: Promise<{ token: string }>;
}

export default function PublicSharePage({ params }: SharePageProps) {
  const resolvedParams = use(params);
  const token = resolvedParams.token;

  const [meeting, setMeeting] = useState<PublicMeetingResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setIsLoading(true);
    setErrorStatus(null);
    setErrorMessage(null);

    meetingApi
      .getPublicMeeting(token)
      .then((data) => {
        setMeeting(data);
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "Failed to load shared meeting";
        if (msg.includes("410") || msg.toLowerCase().includes("expired")) {
          setErrorStatus(410);
          setErrorMessage("This share link has expired.");
        } else {
          setErrorStatus(404);
          setErrorMessage("This share link is invalid or has been disabled by the meeting owner.");
        }
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [token]);

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return "Recent";
    try {
      return new Date(isoString).toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  const getPriorityBadgeClass = (priority: string) => {
    switch (priority.toLowerCase()) {
      case "high":
        return "bg-red-500/15 text-red-300 border-red-500/30";
      case "medium":
        return "bg-amber-500/15 text-amber-300 border-amber-500/30";
      case "low":
        return "bg-blue-500/15 text-blue-300 border-blue-500/30";
      default:
        return "bg-slate-800 text-slate-400 border-slate-700";
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status.toLowerCase()) {
      case "done":
        return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
      case "in_progress":
        return "bg-cyan-500/15 text-cyan-300 border-cyan-500/30";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-cyan-500/30">
      {/* Top Navbar */}
      <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/25 text-cyan-400">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <span className="font-semibold text-sm tracking-tight text-slate-100">
                Meeting Intelligence
              </span>
              <span className="hidden sm:inline-block ml-2 text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                Public Share View
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-400 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-full">
              <Globe className="h-3.5 w-3.5 text-emerald-400" />
              <span>Read-Only Stakeholder Access</span>
            </div>
            <Link
              href="/login"
              className="text-xs font-medium text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1"
            >
              Sign In <ExternalLink className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 mx-auto w-full max-w-6xl px-4 sm:px-6 py-8">
        {isLoading ? (
          <div className="space-y-6">
            <SkeletonLoader className="h-20 w-3/4 rounded-2xl" />
            <SkeletonLoader className="h-64 w-full rounded-2xl" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <SkeletonLoader className="h-48 rounded-xl" />
              <SkeletonLoader className="h-48 rounded-xl" />
            </div>
          </div>
        ) : errorStatus ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 mb-4">
              <AlertTriangle className="h-8 w-8" />
            </div>
            <h1 className="text-xl font-bold text-slate-100 mb-2">
              {errorStatus === 410 ? "Share Link Expired" : "Meeting Link Unavailable"}
            </h1>
            <p className="text-sm text-slate-400 max-w-md mb-6">{errorMessage}</p>
            <Link
              href="/"
              className="rounded-lg bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-400 transition-colors"
            >
              Return to Homepage
            </Link>
          </div>
        ) : meeting ? (
          <div className="space-y-8 animate-in fade-in duration-300">
            {/* Meeting Header */}
            <div className="border-b border-slate-800/80 pb-6">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-400 border border-cyan-500/25">
                  <Sparkles className="h-3.5 w-3.5" />
                  AI Intelligence Report
                </span>
                <span className="text-xs text-slate-400 flex items-center gap-1.5">
                  <Calendar className="h-3.5 w-3.5" />
                  {formatDate(meeting.created_at)}
                </span>
                <span className="text-xs text-slate-400 flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5" />
                  {meeting.duration_minutes} mins
                </span>
              </div>

              <h1 className="text-2xl sm:text-3xl font-bold text-slate-100 tracking-tight">
                {meeting.title}
              </h1>

              {/* Short summary banner */}
              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-sm leading-relaxed text-slate-300">
                <span className="font-semibold text-cyan-300 block mb-1">Executive Summary:</span>
                {meeting.short_summary}
              </div>
            </div>

            {/* Synchronized Audio Player */}
            <div>
              <AudioPlayer
                audioUrl={`${API_BASE_URL}/public/share/${token}/audio`}
                diarizedTranscript={meeting.diarized_transcript}
                plainTranscript={meeting.transcript}
                transcriptWords={meeting.transcript_words}
              />
            </div>

            {/* Two-Column Grid: Detailed Summary & Action Items */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Detailed Summary (2 Columns) */}
              <div className="lg:col-span-2 space-y-6">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl backdrop-blur-sm">
                  <div className="flex items-center gap-2 mb-4 text-slate-200 font-semibold">
                    <FileText className="h-5 w-5 text-cyan-400" />
                    <h3>Detailed Meeting Discussion</h3>
                  </div>
                  <div className="prose prose-invert max-w-none text-sm leading-7 text-slate-300 whitespace-pre-line">
                    {meeting.detailed_summary}
                  </div>
                </div>

                {/* Key Decisions */}
                {meeting.decisions && meeting.decisions.length > 0 && (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl backdrop-blur-sm">
                    <div className="flex items-center gap-2 mb-4 text-slate-200 font-semibold">
                      <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                      <h3>Key Decisions Agreed ({meeting.decisions.length})</h3>
                    </div>
                    <ul className="space-y-3">
                      {meeting.decisions.map((decision, idx) => (
                        <li
                          key={decision.id || idx}
                          className="flex items-start gap-3 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3.5 text-sm"
                        >
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 text-xs font-bold mt-0.5">
                            {idx + 1}
                          </span>
                          <div className="flex-1">
                            <p className="font-medium text-slate-200">{decision.description}</p>
                            {decision.context && (
                              <p className="mt-1 text-xs text-slate-400">{decision.context}</p>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Sidebar: Action Items & Participants (1 Column) */}
              <div className="space-y-6">
                {/* Action Items */}
                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl backdrop-blur-sm">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2 text-slate-200 font-semibold">
                      <ListTodo className="h-5 w-5 text-cyan-400" />
                      <h3>Action Items</h3>
                    </div>
                    <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-800 text-cyan-400">
                      {meeting.action_items.length}
                    </span>
                  </div>

                  {meeting.action_items.length === 0 ? (
                    <p className="text-xs text-slate-500 italic">No action items detected.</p>
                  ) : (
                    <div className="space-y-3">
                      {meeting.action_items.map((item, idx) => (
                        <div
                          key={item.id || idx}
                          className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-3.5 space-y-2"
                        >
                          <p className="text-sm font-medium text-slate-200 leading-snug">
                            {item.description}
                          </p>
                          <div className="flex flex-wrap items-center gap-2 text-xs">
                            <span className="rounded bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300 font-mono">
                              @{item.owner}
                            </span>
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[10px] uppercase font-bold tracking-wider ${getPriorityBadgeClass(
                                item.priority
                              )}`}
                            >
                              {item.priority}
                            </span>
                            <span
                              className={`rounded-full border px-2 py-0.5 text-[10px] capitalize ${getStatusBadgeClass(
                                item.status
                              )}`}
                            >
                              {item.status.replace("_", " ")}
                            </span>
                            {item.due_date && (
                              <span className="text-[11px] text-slate-400 ml-auto font-mono">
                                Due: {item.due_date}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Participants */}
                {meeting.participants && meeting.participants.length > 0 && (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-xl backdrop-blur-sm">
                    <div className="flex items-center gap-2 mb-4 text-slate-200 font-semibold">
                      <Users className="h-5 w-5 text-cyan-400" />
                      <h3>Participants ({meeting.participants.length})</h3>
                    </div>
                    <ul className="space-y-2.5">
                      {meeting.participants.map((participant, idx) => (
                        <li
                          key={participant.id || idx}
                          className="flex items-center justify-between rounded-lg bg-slate-950/50 p-2.5 text-xs"
                        >
                          <span className="font-medium text-slate-200">{participant.name}</span>
                          <span className="text-slate-400 font-mono text-[11px]">
                            {participant.email || participant.speaker_label || "Attendee"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950/60 py-6 text-center text-xs text-slate-500">
        <p>Meeting Intelligence Agent — Autonomous multi-agent pipeline for audio intelligence.</p>
      </footer>
    </div>
  );
}
