import { useState } from "react";
import { ArrowCounterClockwise, CheckSquare } from "@phosphor-icons/react";
import { SOURCES, canonicalSource, sourceIcon } from "./icons";
import type { SourceSelection } from "../lib/sourceFilter";
import { allSources, materializeSources } from "../lib/sourceFilter";
import { cn } from "../lib/utils";
import { IconButton } from "./ui/icon-button";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

/* Multi-select source filter for the inbox rail (#126): a named group of
   checkboxes, several on at once. SourceFilter stays single-valued for / and
   /library. */
export function SourceSelect({
  selection,
  onChange,
}: {
  selection: SourceSelection;
  onChange: (next: SourceSelection) => void;
}) {
  const active = materializeSources(selection, SOURCES);
  const everything = allSources(SOURCES);

  const toggle = (source: string) => {
    const next = new Set(active);
    const name = canonicalSource(source);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-2">
      <div
        className="grid grid-cols-4 gap-1.5"
        role="group"
        aria-label="Filter by source"
      >
        {SOURCES.map((s) => (
          <SourceTile
            key={s}
            source={s}
            checked={active.has(canonicalSource(s))}
            onToggle={() => toggle(s)}
          />
        ))}
      </div>
      <div className="flex gap-2">
        <IconButton
          label="Select all sources"
          variant="secondary"
          className="flex-1"
          onClick={() => onChange(everything)}
          disabled={active.size === everything.size}
        >
          <CheckSquare />
        </IconButton>
        <IconButton
          label="Restore default sources"
          variant="secondary"
          className="flex-1"
          onClick={() => onChange(null)}
          // Not "select everything": null re-applies DEFAULT_HIDDEN.
          disabled={selection === null}
        >
          <ArrowCounterClockwise />
        </IconButton>
      </div>
    </div>
  );
}

function SourceTile({
  source,
  checked,
  onToggle,
}: {
  source: string;
  checked: boolean;
  onToggle: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  return (
    // Controlled: Radix closes its tooltip on click, but a tile must keep
    // disclosing its name while the checkbox holds focus after a click.
    <Tooltip open={hovered || focused}>
      <TooltipTrigger asChild>
        <label
          className={cn(
            "relative grid aspect-square min-h-11 min-w-11 cursor-pointer place-items-center rounded-lg border border-line bg-bg1 transition-[border-color,background-color] duration-[180ms] ease-hub hover:border-accent has-focus-visible:outline-2 has-focus-visible:outline-offset-1 has-focus-visible:outline-accent [&>svg]:opacity-35 [&>svg]:grayscale",
            checked &&
              "border-accent/40 bg-accent/10 [&>svg]:opacity-100 [&>svg]:grayscale-0",
          )}
          onPointerEnter={() => setHovered(true)}
          onPointerLeave={() => setHovered(false)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
        >
          {sourceIcon(source, 22)}
          <span className="sr-only">{source}</span>
          {/* Last in DOM so it paints above the glyph and is the pointer target. */}
          <input
            type="checkbox"
            className="absolute inset-0 cursor-pointer appearance-none rounded-lg outline-none"
            checked={checked}
            onChange={onToggle}
          />
        </label>
      </TooltipTrigger>
      <TooltipContent>{source}</TooltipContent>
    </Tooltip>
  );
}
