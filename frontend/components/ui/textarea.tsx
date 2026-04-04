import * as React from "react";
import { cn } from "@/lib/utils";

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          "min-h-24 w-full rounded-xl border border-brand-cream-200 bg-white px-4 py-3 text-sm text-brand-charcoal-900 shadow-sm outline-none placeholder:text-brand-charcoal-700/50 focus:border-brand-cream-300 focus:ring-2 focus:ring-brand-cream-100",
          className
        )}
        {...props}
      />
    );
  }
);

Textarea.displayName = "Textarea";
