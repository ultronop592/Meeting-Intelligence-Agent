import * as React from "react";
import { cn } from "@/lib/utils";

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-[10px] border border-border bg-surface-2 px-3 text-sm text-foreground outline-none placeholder:text-text-tertiary focus:border-accent",
        className
      )}
      {...props}
    />
  );
});

Input.displayName = "Input";
