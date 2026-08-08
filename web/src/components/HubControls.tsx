import type { ReactNode } from "react";
import { cn } from "../lib/utils";
import { useChromeVisible } from "../lib/chrome";

// Page controls render inside the page, never in the nav bar.
export function HubControls({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const chrome = useChromeVisible();
  if (!chrome) return null;
  return (
    <div
      className={cn("flex flex-wrap items-center gap-2.5 px-4 pt-4", className)}
    >
      {children}
    </div>
  );
}
