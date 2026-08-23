import { SOURCES, sourceIcon } from "./icons";
import { cn } from "../lib/utils";
import { Toolbar, ToolbarButton } from "./ui/toolbar";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";

// Single-select source filter for / and /library. Radix Toolbar gives the
// chips one tab stop and arrow-key roving; the tooltip only echoes the name.
export function SourceFilter({
  value,
  onChange,
}: {
  // The property needs the explicit `| undefined` under
  // exactOptionalPropertyTypes; the callback parameter does not.
  value?: string | undefined;
  onChange: (s?: string) => void;
}) {
  // Own provider: the chips mount in HubControls, outside any page-level one.
  return (
    <TooltipProvider>
      <Toolbar label="Filter by source" className="flex-wrap">
        {SOURCES.map((s) => {
          const on = value === s;
          return (
            <Tooltip key={s}>
              <TooltipTrigger asChild>
                <ToolbarButton
                  size="icon"
                  className={cn(
                    "[&>svg]:opacity-40 [&>svg]:grayscale",
                    on &&
                      "border-accent/40 bg-accent/10 [&>svg]:opacity-100 [&>svg]:grayscale-0",
                  )}
                  aria-pressed={on}
                  onClick={() => onChange(on ? undefined : s)}
                >
                  {sourceIcon(s, 20)}
                  <span className="sr-only">{s}</span>
                </ToolbarButton>
              </TooltipTrigger>
              <TooltipContent>{s}</TooltipContent>
            </Tooltip>
          );
        })}
      </Toolbar>
    </TooltipProvider>
  );
}
