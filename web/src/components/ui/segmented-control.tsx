import { useId, type ComponentProps } from "react";
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import type { ToggleGroupSingleProps } from "@radix-ui/react-toggle-group";
import { cn } from "@/lib/utils";

type SegmentedControlProps = Omit<
  ToggleGroupSingleProps,
  "type" | "value" | "defaultValue" | "onValueChange" | "aria-label" | "aria-labelledby"
> & {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
};

function SegmentedControl({
  className,
  label,
  value,
  onValueChange,
  orientation = "horizontal",
  loop = true,
  ...props
}: SegmentedControlProps) {
  const labelId = useId();

  return (
    <div data-slot="segmented-control" className="flex flex-wrap items-center gap-2">
      <span id={labelId} className="font-data text-sm tracking-[0.03em] text-ink2 lowercase">
        {label}
      </span>
      <ToggleGroupPrimitive.Root
        data-slot="segmented-control-list"
        type="single"
        value={value}
        orientation={orientation}
        loop={loop}
        aria-labelledby={labelId}
        onValueChange={(nextValue) => {
          if (nextValue) onValueChange(nextValue);
        }}
        className={cn(
          "inline-flex items-center gap-2 rounded-lg border border-line bg-bg1 p-1 data-[orientation=vertical]:flex-col",
          className,
        )}
        {...props}
      />
    </div>
  );
}

function SegmentedControlItem({
  className,
  ...props
}: ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  return (
    <ToggleGroupPrimitive.Item
      data-slot="segmented-control-item"
      className={cn(
        "inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-transparent px-3 py-2 font-data text-sm leading-none tracking-[0.03em] text-ink2 lowercase transition-[color,background-color,border-color] duration-[180ms] ease-hub hover:bg-bg3 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50 data-[state=on]:border-accent data-[state=on]:bg-accent data-[state=on]:font-semibold data-[state=on]:text-bg0 data-[state=on]:underline data-[state=on]:decoration-2 data-[state=on]:underline-offset-4",
        className,
      )}
      {...props}
    />
  );
}

export { SegmentedControl, SegmentedControlItem };
export type { SegmentedControlProps };
