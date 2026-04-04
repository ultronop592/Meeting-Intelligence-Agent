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
    <aside className="flex h-full w-full flex-col border-r border-brand-cream-200 bg-brand-cream-50">
      <div className="px-4 pb-3 pt-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-brand-charcoal-700/60">
            Meeting Intelligence
          </p>
          <h1 className="mt-1 text-base font-semibold text-brand-charcoal-900">
            Workspace
          </h1>
        </div>
      </div>

      <div className="px-4 pb-3">
        <Button size="sm" className="w-full" onClick={onNewMeeting}>
          New conversation
        </Button>
      </div>

      <div className="flex-1 overflow-auto px-3 pb-4">
        {loading ? (
          <p className="text-sm text-brand-charcoal-700/60">
            Loading history...
          </p>
        ) : null}
        {!loading && meetings.length === 0 ? (
          <p className="text-sm text-brand-charcoal-700/60">No meetings yet.</p>
        ) : null}

        <ul className="space-y-2">
          {meetings.map((meeting) => (
            <li key={meeting.id}>
              <button
                className={cn(
                  "w-full rounded-2xl border p-3 text-left transition",
                  selectedId === meeting.id
                    ? "border-brand-cream-300 bg-white shadow-sm"
                    : "border-brand-cream-200 bg-white/80 hover:border-brand-cream-300 hover:bg-white",
                )}
                onClick={() => onSelect(meeting.id)}
              >
                <p className="line-clamp-1 text-sm font-medium text-brand-charcoal-900">
                  {meeting.title || "Untitled meeting"}
                </p>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-brand-charcoal-700/60">
                  {meeting.short_summary}
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <Badge>{meeting.action_items_count} tasks</Badge>
                  <span className="text-[11px] text-brand-charcoal-700/40">
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
