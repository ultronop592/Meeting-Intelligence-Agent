import * as React from "react";
import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          "min-h-24 w-full rounded-[12px] border border-border bg-surface-2 px-4 py-3 text-sm text-foreground outline-none placeholder:text-text-tertiary focus:border-accent",
          className
        )}
        {...props}
      />
    );
  }
);

Textarea.displayName = "Textarea";
