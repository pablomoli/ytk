import type { ComponentProps, ReactNode } from "react";
import { Button, type ButtonProps } from "./button";
import { Tooltip, TooltipContent, TooltipTrigger } from "./tooltip";

type IconButtonProps = Omit<ButtonProps, "aria-label" | "children" | "size"> & {
  label: string;
  children: ReactNode;
  tooltipSide?: ComponentProps<typeof TooltipContent>["side"];
};

function IconButton({
  label,
  children,
  variant = "ghost",
  tooltipSide = "top",
  ...props
}: IconButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          data-slot="icon-button"
          type="button"
          size="icon"
          variant={variant}
          aria-label={label}
          {...props}
        >
          <span aria-hidden="true" className="inline-flex [&>svg]:size-5 [&>svg]:shrink-0">
            {children}
          </span>
        </Button>
      </TooltipTrigger>
      <TooltipContent side={tooltipSide}>{label}</TooltipContent>
    </Tooltip>
  );
}

export { IconButton };
export type { IconButtonProps };
