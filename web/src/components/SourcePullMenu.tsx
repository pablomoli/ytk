import { useState } from "react";
import { PULL_SOURCES } from "./icons";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

/* A popover next to the "refresh" button for pulling only chosen sources.
   The plain refresh still pulls everything; this is the "just check Instagram
   right now" path. Selection is local state — nothing to persist for a one-off
   action. Radix portals and collision-positions the popover, which is what
   keeps the confirm button reachable inside the rail's clipped scroller
   (#125-class failure). */
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

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button className="btn caret" aria-label="pull specific sources" disabled={disabled}>
          &#9662;
        </button>
      </PopoverTrigger>
      <PopoverContent className="flex flex-col gap-[0.15rem]">
        <div className="mb-1 text-[0.7rem] tracking-[0.04em] text-mute uppercase">pull only</div>
        {PULL_SOURCES.map((s) => (
          <label
            key={s}
            className="flex cursor-pointer items-center gap-[0.45rem] px-[0.1rem] py-[0.15rem] text-[0.82rem]"
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
        <button
          className="btn primary mt-[0.4rem] px-[0.7rem] py-[0.32rem] text-[0.8rem]"
          onClick={pull}
          disabled={chosen.size === 0}
        >
          pull {chosen.size > 0 ? `(${chosen.size})` : ""}
        </button>
      </PopoverContent>
    </Popover>
  );
}
