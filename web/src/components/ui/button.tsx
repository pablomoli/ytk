import type { ComponentProps } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-2 rounded-lg border font-data text-sm leading-none tracking-[0.03em] text-nowrap lowercase select-none transition-[color,background-color,border-color] duration-[180ms] ease-hub focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-accent bg-accent text-bg0 hover:bg-accent/90",
        secondary: "border-line bg-bg3 text-ink hover:border-ink2/40 hover:bg-bg2",
        outline: "border-line bg-transparent text-ink2 hover:border-ink2/40 hover:text-ink",
        ghost: "border-transparent bg-transparent text-ink2 hover:bg-bg3 hover:text-ink",
      },
      size: {
        default: "px-4 py-2",
        sm: "px-3 py-1.5 text-[0.8125rem]",
        lg: "px-6 py-2.5",
        icon: "size-11 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants>;

function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return (
    <button
      data-slot="button"
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Button, buttonVariants };
export type { ButtonProps };
