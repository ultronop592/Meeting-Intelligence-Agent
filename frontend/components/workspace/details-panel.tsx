import type { MeetingDetailResponse } from "@/types/api";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type DetailsPanelProps = {
  detail: MeetingDetailResponse | null;
};

export function DetailsPanel({ detail }: DetailsPanelProps) {
  if (!detail) {
    return (
      <aside className="hidden border-l border-brand-cream-200 bg-brand-cream-100 p-4 xl:block">
        <p className="text-sm text-brand-charcoal-700/60">
          Select a meeting to view insights.
        </p>
      </aside>
    );
  }

  return (
    <aside className="hidden overflow-auto border-l border-brand-cream-200 bg-brand-cream-100 p-4 xl:block">
      <div className="space-y-3">
        <Card>
          <CardHeader>
            <h3 className="text-sm font-semibold text-brand-charcoal-900">
              Summary
            </h3>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-brand-charcoal-700">
              {detail.meeting.short_summary}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h3 className="text-sm font-semibold text-brand-charcoal-900">
              Action Items
            </h3>
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
                className="rounded-xl border border-brand-cream-200 bg-white p-2.5"
              >
                <p className="text-xs font-medium text-brand-charcoal-900">
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
            <h3 className="text-sm font-semibold text-brand-charcoal-900">
              Decisions
            </h3>
          </CardHeader>
          <CardContent className="space-y-2">
            {detail.decisions.length === 0 ? (
              <p className="text-sm text-brand-charcoal-700/60">
                No decisions extracted.
              </p>
            ) : null}
            {detail.decisions.map((decision) => (
              <div
                key={decision.id}
                className="rounded-xl border border-brand-cream-200 bg-white p-2.5"
              >
                <p className="text-xs font-medium text-brand-charcoal-900">
                  {decision.description}
                </p>
                <p className="text-xs text-brand-charcoal-700/60">
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
