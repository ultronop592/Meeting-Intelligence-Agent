"use client";

import React from "react";
import {
  Mic,
  Brain,
  FileText,
  Database,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Radio,
  Clock,
  Sparkles,
} from "lucide-react";

export type PipelineNodeState = "pending" | "running" | "completed" | "failed";

export interface PipelineNodeInfo {
  id: string;
  name: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  aliases: string[];
}

export const PIPELINE_NODES: PipelineNodeInfo[] = [
  {
    id: "transcribe_audio",
    name: "Transcription",
    label: "Whisper Speech-to-Text",
    description: "FFmpeg chunking & Whisper Large-v3 audio transcription",
    icon: Mic,
    aliases: ["upload", "transcribe_audio", "transcribe"],
  },
  {
    id: "extract_information",
    name: "Cognitive Extraction",
    label: "Actions & Decisions",
    description: "Extracts owners, due dates, priorities & key decisions",
    icon: Brain,
    aliases: ["extract_information", "extract"],
  },
  {
    id: "generate_summary",
    name: "Synthesis",
    label: "Executive Summary",
    description: "Multi-LLM executive & detailed meeting summary",
    icon: FileText,
    aliases: ["generate_summary", "summary"],
  },
  {
    id: "save_to_database",
    name: "Vector Memory",
    label: "Persistence & RAG Indexing",
    description: "Neon Postgres persistence & pgvector embedding",
    icon: Database,
    aliases: ["save_to_database", "save"],
  },
];

interface PipelineTrackerProps {
  completedNodes: string[];
  status?: string;
  isRealtime?: boolean;
  durationMs?: number | null;
  nodeTimings?: Record<string, { duration_ms?: number | null }>;
}

export function PipelineTracker({
  completedNodes = [],
  status = "processing",
  isRealtime = false,
  durationMs,
  nodeTimings = {},
}: PipelineTrackerProps) {
  // Determine each node's state
  const getNodeState = (node: PipelineNodeInfo, index: number): PipelineNodeState => {
    const isCompleted = node.aliases.some((alias) => completedNodes.includes(alias));
    if (isCompleted) return "completed";

    if (status === "failed") {
      // Find where failure occurred
      const prevNodesCompleted = PIPELINE_NODES.slice(0, index).every((p) =>
        p.aliases.some((alias) => completedNodes.includes(alias))
      );
      return prevNodesCompleted ? "failed" : "pending";
    }

    if (status === "processing") {
      // Check if previous nodes completed
      const prevCompleted = index === 0 || PIPELINE_NODES.slice(0, index).every((p) =>
        p.aliases.some((alias) => completedNodes.includes(alias))
      );
      if (prevCompleted) return "running";
    }

    return "pending";
  };

  const completedCount = PIPELINE_NODES.filter((n) =>
    n.aliases.some((a) => completedNodes.includes(a))
  ).length;
  const progressPercent = Math.round((completedCount / PIPELINE_NODES.length) * 100);

  return (
    <div className="rounded-2xl border border-border/80 bg-surface p-5 shadow-xs transition-all">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 pb-3.5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent/15 text-accent">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-foreground">
              LangGraph Multi-Agent Pipeline
            </h3>
            <p className="text-xs text-text-tertiary">
              4-Node Cognitive Processing Architecture
            </p>
          </div>
        </div>

        {/* Real-time Indicator & Timer */}
        <div className="flex items-center gap-3">
          {isRealtime ? (
            <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-medium text-emerald-500">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              <span>Live WebSocket</span>
            </div>
          ) : (
            <div className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 px-2.5 py-0.5 text-[11px] text-text-secondary">
              <Radio className="h-3 w-3 text-text-tertiary" />
              <span>Polling Fallback</span>
            </div>
          )}

          {durationMs != null && (
            <div className="flex items-center gap-1 text-xs text-text-tertiary">
              <Clock className="h-3 w-3" />
              <span>{Math.round(durationMs / 1000)}s</span>
            </div>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mt-4 mb-5">
        <div className="flex items-center justify-between text-xs text-text-tertiary mb-1.5">
          <span className="font-medium">Pipeline Progress</span>
          <span className="font-semibold text-foreground">{progressPercent}%</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
          <div
            className="h-full bg-accent transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Node Stepper Grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {PIPELINE_NODES.map((node, index) => {
          const state = getNodeState(node, index);
          const NodeIcon = node.icon;
          const timing = nodeTimings[node.id]?.duration_ms;

          return (
            <div
              key={node.id}
              className={`relative flex flex-col justify-between rounded-xl border p-3.5 transition-all ${
                state === "running"
                  ? "border-accent bg-accent/5 ring-1 ring-accent/30 shadow-xs"
                  : state === "completed"
                  ? "border-emerald-500/25 bg-emerald-500/5 text-foreground"
                  : state === "failed"
                  ? "border-rose-500/30 bg-rose-500/5 text-foreground"
                  : "border-border/60 bg-surface-2/40 text-text-tertiary"
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div
                    className={`flex h-7 w-7 items-center justify-center rounded-lg ${
                      state === "running"
                        ? "bg-accent/20 text-accent"
                        : state === "completed"
                        ? "bg-emerald-500/20 text-emerald-500"
                        : state === "failed"
                        ? "bg-rose-500/20 text-rose-500"
                        : "bg-surface text-text-tertiary"
                    }`}
                  >
                    <NodeIcon className="h-3.5 w-3.5" />
                  </div>

                  {state === "completed" ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-500">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Done
                    </span>
                  ) : state === "running" ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent animate-pulse">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Active
                    </span>
                  ) : state === "failed" ? (
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-500">
                      <AlertCircle className="h-3.5 w-3.5" /> Failed
                    </span>
                  ) : (
                    <span className="text-[11px] text-text-tertiary">Pending</span>
                  )}
                </div>

                <p className="text-xs font-semibold text-foreground">{node.name}</p>
                <p className="text-[11px] text-text-secondary mt-0.5">{node.label}</p>
              </div>

              {timing != null && (
                <div className="mt-2.5 pt-2 border-t border-border/50 text-[10px] text-text-tertiary">
                  Took {Math.round(timing / 1000)}s
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
