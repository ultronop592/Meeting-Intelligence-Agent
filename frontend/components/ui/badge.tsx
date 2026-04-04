import { cn } from "@/lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement>;

export function Badge({ className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-brand-orange-500/30 bg-brand-orange-500/10 px-2.5 py-0.5 text-xs font-semibold text-brand-orange-700",
        className
      )}
      {...props}
    />
  );
}
