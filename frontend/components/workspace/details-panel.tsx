import type { MeetingDetailResponse } from "@/types/api";
import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type DetailsPanelProps = {
  detail: MeetingDetailResponse | null;
  isOpen: boolean;
  onToggle: () => void;
};

export function DetailsPanel({ detail, isOpen, onToggle }: DetailsPanelProps) {
  if (!isOpen) {
    return (
      <aside className="hidden border-l border-border bg-surface p-2 xl:block">
        <Button variant="ghost" size="sm" onClick={onToggle} aria-label="Open insights panel" className="w-full justify-start">
          <ChevronRight className="mr-1 h-4 w-4" /> Insights
        </Button>
      </aside>
    );
  }

  if (!detail) {
    return (
      <aside className="hidden border-l border-border bg-surface p-4 xl:block">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-foreground">Insights</h3>
          <Button variant="ghost" size="sm" onClick={onToggle} aria-label="Collapse insights panel">
            Hide
          </Button>
        </div>
        <p className="rounded-[12px] border border-border bg-surface-2 p-3 text-sm text-text-secondary">
          Select a meeting to view insights.
        </p>
      </aside>
    );
  }

  return (
    <aside className="hidden overflow-auto border-l border-border bg-surface p-4 xl:block">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Insights</h3>
        <Button variant="ghost" size="sm" onClick={onToggle} aria-label="Collapse insights panel">
          Hide
        </Button>
      </div>
      <div className="space-y-3">
        <Card>
          <CardHeader>
            <h3 className="text-sm font-semibold text-foreground">
              Summary
            </h3>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-text-secondary">
              {detail.meeting.short_summary}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="text-sm font-semibold text-foreground">
              Action Items
            </h3>
          </CardHeader>
          <CardContent className="space-y-2">
            {detail.action_items.length === 0 ? (
              <p className="text-sm text-text-secondary">
                No action items.
              </p>
            ) : null}
            {detail.action_items.map((item) => (
              <div
                key={item.id}
                className="rounded-[10px] border border-border bg-surface-2 p-2.5"
              >
                <p className="text-xs font-medium text-foreground">
                  {item.description}
                </p>
                <div className="mt-1 flex gap-2">
                  <Badge>{item.priority}</Badge>
                  <Badge>{item.status}</Badge>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="text-sm font-semibold text-foreground">
              Decisions
            </h3>
          </CardHeader>
          <CardContent className="space-y-2">
            {detail.decisions.length === 0 ? (
              <p className="text-sm text-text-secondary">
                No decisions extracted.
              </p>
            ) : null}
            {detail.decisions.map((decision) => (
              <div
                key={decision.id}
                className="rounded-[10px] border border-border bg-surface-2 p-2.5"
              >
                <p className="text-xs font-medium text-foreground">
                  {decision.description}
                </p>
                <p className="text-xs text-text-secondary">
                  {decision.context}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </aside>
  );
}
