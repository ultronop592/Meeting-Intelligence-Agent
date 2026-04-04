import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-xl text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 cursor-pointer active:scale-[0.98]",
  {
    variants: {
      variant: {
        default: "bg-brand-charcoal-900 text-brand-cream-50 hover:bg-brand-charcoal-800 shadow-sm",
        primary: "bg-brand-orange-500 text-white hover:bg-brand-orange-600 shadow-sm",
        outline: "border border-brand-cream-200 bg-white text-brand-charcoal-900 hover:bg-brand-cream-50",
        ghost: "text-brand-charcoal-800 hover:bg-brand-cream-100",
        danger: "bg-rose-600 text-white hover:bg-rose-500 shadow-sm",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-8 px-3 text-xs rounded-lg",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);

Button.displayName = "Button";

export { Button, buttonVariants };
