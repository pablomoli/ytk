import type { ComponentProps } from "react";
import * as ToolbarPrimitive from "@radix-ui/react-toolbar";
import type { VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { buttonVariants } from "./button";

type ToolbarProps = Omit<ComponentProps<typeof ToolbarPrimitive.Root>, "aria-label"> & {
  label: string;
};

function Toolbar({
  className,
  label,
  orientation = "horizontal",
  loop = true,
  ...props
}: ToolbarProps) {
  return (
    <ToolbarPrimitive.Root
      data-slot="toolbar"
      aria-label={label}
      orientation={orientation}
      loop={loop}
      className={cn(
        "inline-flex min-h-11 items-center gap-2 rounded-lg border border-line bg-bg1 p-1",
        className,
      )}
      {...props}
    />
  );
}

type ToolbarButtonProps = ComponentProps<typeof ToolbarPrimitive.Button> &
  VariantProps<typeof buttonVariants>;

// Radix owns the roving tabindex and Arrow/Home/End focus contract for these items.
function ToolbarButton({
  className,
  variant = "ghost",
  size = "default",
  ...props
}: ToolbarButtonProps) {
  return (
    <ToolbarPrimitive.Button
      data-slot="toolbar-button"
      type="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

function ToolbarLink({ className, ...props }: ComponentProps<typeof ToolbarPrimitive.Link>) {
  return (
    <ToolbarPrimitive.Link
      data-slot="toolbar-link"
      className={cn(buttonVariants({ variant: "ghost" }), className)}
      {...props}
    />
  );
}

function ToolbarSeparator({
  className,
  ...props
}: ComponentProps<typeof ToolbarPrimitive.Separator>) {
  return (
    <ToolbarPrimitive.Separator
      data-slot="toolbar-separator"
      className={cn("mx-1 h-6 w-px bg-line", className)}
      {...props}
    />
  );
}

export { Toolbar, ToolbarButton, ToolbarLink, ToolbarSeparator };
export type { ToolbarButtonProps, ToolbarProps };
