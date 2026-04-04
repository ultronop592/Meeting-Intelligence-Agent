import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-lg border border-brand-cream-200 bg-white px-3 text-sm text-brand-charcoal-900 shadow-sm outline-none placeholder:text-brand-charcoal-700/50 focus:border-brand-cream-300 focus:ring-2 focus:ring-brand-cream-100",
        className
      )}
      {...props}
    />
  );
});

Input.displayName = "Input";
