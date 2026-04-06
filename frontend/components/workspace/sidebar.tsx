import type { MeetingListItem } from "@/types/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

type SidebarProps = {
  meetings: MeetingListItem[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNewMeeting: () => void;
};

export function Sidebar({
  meetings,
  loading,
  selectedId,
  onSelect,
  onNewMeeting,
}: SidebarProps) {
  return (
    <aside className="flex h-full w-full flex-col border-r border-border bg-surface p-3">
      <div className="px-2 pb-4 pt-2">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-text-tertiary">
            Meeting Intelligence
          </p>
          <h1 className="mt-1 text-base font-semibold text-foreground">
            Workspace
          </h1>
        </div>
      </div>

      <div className="px-2 pb-4">
        <Button size="sm" className="w-full" onClick={onNewMeeting} aria-label="Create a new meeting thread">
          New conversation
        </Button>
      </div>

      <div className="flex-1 overflow-auto px-2 pb-2">
        {loading ? (
          <div className="space-y-2" aria-label="Loading meetings">
            {Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="h-20 animate-pulse rounded-[12px] border border-border bg-surface-2" />
            ))}
          </div>
        ) : null}
        {!loading && meetings.length === 0 ? (
          <p className="rounded-[12px] border border-border bg-surface-2 p-3 text-sm text-text-secondary">
            No meetings yet.
          </p>
        ) : null}

        <ul className="space-y-2">
          {meetings.map((meeting) => (
            <li key={meeting.id}>
              <button
                type="button"
                aria-label={`Open meeting ${meeting.title || "Untitled meeting"}`}
                className={cn(
                  "w-full rounded-[12px] border p-3 text-left transition-colors duration-200",
                  selectedId === meeting.id
                    ? "border-accent bg-surface-3"
                    : "border-border bg-surface-2 hover:bg-surface-3",
                )}
                onClick={() => onSelect(meeting.id)}
              >
                <p className="line-clamp-1 text-sm font-medium text-foreground">
                  {meeting.title || "Untitled meeting"}
                </p>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-text-secondary">
                  {meeting.short_summary}
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <Badge>{meeting.action_items_count} tasks</Badge>
                  <span className="text-[11px] text-text-tertiary">
                    {meeting.audio_filename}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
