import Link from "next/link";
import type { MeetingListItem } from "@/types/api";
import { StatusBadge } from "@/components/ui/status-badge";

function formatDate(value: string | null) {
  if (!value) return "Pending";
  const date = new Date(value);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function MeetingCard({ meeting }: { meeting: MeetingListItem }) {
  return (
    <Link
      href={`/meetings/${meeting.id}`}
      className="group flex h-full flex-col rounded-[16px] border border-border bg-surface p-4 transition-all hover:-translate-y-0.5 hover:border-accent/60"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">
            {meeting.title || "Untitled meeting"}
          </p>
          <p className="mt-1 text-xs text-text-tertiary">{formatDate(meeting.created_at)}</p>
        </div>
        <StatusBadge status="ready" label="Ready" />
      </div>
      <p className="mt-3 line-clamp-3 text-sm text-text-secondary">{meeting.short_summary}</p>
      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-text-tertiary">
        <span>{meeting.duration_minutes} min</span>
        <span>{meeting.action_items_count} action items</span>
      </div>
    </Link>
  );
}
