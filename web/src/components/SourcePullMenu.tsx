import { useState } from "react";
import { CaretDown } from "@phosphor-icons/react";
import { PULL_SOURCES } from "./icons";
import { Button } from "./ui/button";
import { IconButton } from "./ui/icon-button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { TooltipProvider } from "./ui/tooltip";

/* Popover next to "Refresh sources" for pulling only chosen sources. Selection
   is local state: nothing to persist for a one-off action. Radix portals the
   content so the rail's clipped scroller cannot cut off the confirm button. */
export function SourcePullMenu({
  onPull,
  disabled,
}: {
  onPull: (only: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());

  const toggle = (s: string) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  const pull = () => {
    if (chosen.size === 0) return;
    onPull([...chosen]);
    setOpen(false);
  };

  const count = chosen.size;
  return (
    <TooltipProvider>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <IconButton
            label="Pull specific sources"
            variant="secondary"
            disabled={disabled}
          >
            <CaretDown />
          </IconButton>
        </PopoverTrigger>
        <PopoverContent className="flex flex-col gap-0.5">
          <div className="mb-1 text-[0.7rem] tracking-[0.04em] text-mute uppercase">
            pull only
          </div>
          {PULL_SOURCES.map((s) => (
            <label
              key={s}
              className="flex min-h-11 cursor-pointer items-center gap-2 px-0.5 text-[0.82rem]"
            >
              <input
                type="checkbox"
                className="accent-accent"
                checked={chosen.has(s)}
                onChange={() => toggle(s)}
              />
              {s}
            </label>
          ))}
          <Button className="mt-1" onClick={pull} disabled={count === 0}>
            {count === 0
              ? "Pull"
              : `Pull ${count} ${count === 1 ? "source" : "sources"}`}
          </Button>
        </PopoverContent>
      </Popover>
    </TooltipProvider>
  );
}
