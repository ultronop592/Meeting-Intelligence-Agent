import { cn } from "@/lib/utils";

const styles: Record<string, string> = {
  ready: "border-accent/40 bg-accent/15 text-foreground",
  processing: "border-border bg-surface-2 text-text-secondary",
  failed: "border-danger/40 bg-danger/10 text-danger",
};

type StatusBadgeProps = {
  status: "ready" | "processing" | "failed";
  label: string;
};

export function StatusBadge({ status, label }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
        styles[status]
      )}
    >
      {label}
    </span>
  );
}
