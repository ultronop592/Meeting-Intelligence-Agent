import { cn } from "@/lib/utils";

type BadgeProps = React.HTMLAttributes<HTMLSpanElement>;

export function Badge({ className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-accent/35 bg-accent/15 px-2.5 py-0.5 text-xs font-medium text-foreground",
        className
      )}
      {...props}
    />
  );
}
