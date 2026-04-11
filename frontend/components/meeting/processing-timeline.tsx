import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { JobStatus } from "@/types/api";
import { cn } from "@/lib/utils";

type ProcessingTimelineProps = {
  status?: JobStatus;
  completedNodes?: string[];
  errors?: string[];
};

type TimelineNode = {
  key: string;
  label: string;
  aliases: string[];
};

const timelineNodes: TimelineNode[] = [
  {
    key: "transcribe_audio",
    label: "Transcribe audio",
    aliases: ["transcribe_audio", "upload"],
  },
  {
    key: "extract_information",
    label: "Extract decisions and actions",
    aliases: ["extract_information", "process"],
  },
  {
    key: "generate_summary",
    label: "Generate summary",
    aliases: ["generate_summary"],
  },
  {
    key: "save_to_database",
    label: "Save to database",
    aliases: ["save_to_database"],
  },
];

function getNodeState(
  node: TimelineNode,
  status?: JobStatus,
  completedNodes: string[] = []
): "completed" | "active" | "failed" | "pending" {
  const isCompleted = completedNodes.some((done) => node.aliases.includes(done));

  if (isCompleted) {
    return "completed";
  }

  if (status === "failed") {
    return "failed";
  }

  if (status === "processing") {
    return "active";
  }

  return "pending";
}

export function ProcessingTimeline({
  status,
  completedNodes,
  errors,
}: ProcessingTimelineProps) {
  const done = completedNodes ?? [];
  const isLive = status === "processing";

  return (
    <div className="rounded-[16px] border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">Agent pipeline</h3>
        <span className="text-xs text-text-tertiary">
          {isLive ? "Running" : status ? "Latest run" : "Idle"}
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {timelineNodes.map((node) => {
          const state = getNodeState(node, status, done);

          return (
            <div key={node.key} className="flex items-start gap-3">
              <div className="mt-0.5">
                {state === "completed" ? (
                  <CheckCircle2 className="h-4 w-4 text-accent-strong" />
                ) : state === "active" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-foreground" />
                ) : state === "failed" ? (
                  <XCircle className="h-4 w-4 text-danger" />
                ) : (
                  <Circle className="h-4 w-4 text-text-tertiary" />
                )}
              </div>

              <div>
                <p
                  className={cn(
                    "text-sm",
                    state === "completed" && "text-foreground",
                    state === "active" && "text-foreground",
                    state === "failed" && "text-danger",
                    state === "pending" && "text-text-secondary"
                  )}
                >
                  {node.label}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {errors && errors.length > 0 ? (
        <p className="mt-3 rounded-[10px] border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-danger">
          {errors[0]}
        </p>
      ) : null}
    </div>
  );
}
