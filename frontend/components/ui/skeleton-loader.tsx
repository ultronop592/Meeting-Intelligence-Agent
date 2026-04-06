import { cn } from "@/lib/utils";

type SkeletonLoaderProps = {
  className?: string;
};

export function SkeletonLoader({ className }: SkeletonLoaderProps) {
  return (
    <div className={cn("animate-pulse rounded-[12px] border border-border bg-surface-2", className)} />
  );
}
