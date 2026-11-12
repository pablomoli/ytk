import { useLayoutEffect, useRef, useState } from "react";
import type { PointerEvent, RefObject } from "react";
import type { LayoutName } from "../api/orb";
import type { OrbViewMode } from "../lib/orb/scene";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type Props = {
  searchRef: RefObject<HTMLInputElement | null>;
  settled: unknown; // changes once the face has loaded, so the lens rule measures the final letters
  query: string;
  onQuery: (q: string) => void;
  onEnter: () => void;
  lenses: { name: LayoutName; label: string; title: string }[];
  layout: LayoutName | null;
  onLayout: (name: LayoutName) => void;
  view: OrbViewMode;
  onView: (view: OrbViewMode) => void;
  terrain: boolean;
  onTerrain: (on: boolean) => void;
  library: boolean;
  count: number;
  onLibrary: () => void;
  spread: number;
  onSpread: (x: number) => void;
  themes: { label: string; count: number }[];
  theme: number | null;
  onTheme: (th: number | null) => void;
};

// no preflight in the hub: a button keeps the browser's box unless each property is given back
const WORD = "cursor-pointer appearance-none border-0 bg-transparent p-0 [font:inherit] [letter-spacing:inherit] transition-colors duration-200 ease-hub";
const word = (on: boolean) => `${WORD} ${on ? "text-ink" : "text-ink2/60 hover:text-ink"}`;
// a switch that is on wears the brass rule the lens row slides
const sw = (on: boolean) => `${word(on)} border-b pb-px ${on ? "!border-accent" : "!border-transparent"}`;
const SMALL = "text-[13px]";

const TICKS = 41, MID = (TICKS - 1) / 2;
// the shapes the pending items take along the scale, each named where it holds
const STOPS = [
  { at: -1, label: "dust", title: "the sphere drawn in, the pending items adrift around it" },
  { at: 0, label: "ring", title: "the sphere at rest, the pending items in a ring" },
  { at: 0.5, label: "atom", title: "the ring parted into three orbits" },
  { at: 1, label: "coil", title: "the queue wound into one thread around the sphere, newest at the top" },
];

/* The sphere's size as a ruled scale: rest at the center mark, contract to the
   left, explode to the right. Hand-built because a native range is drawn
   differently by every engine. */
function Scale({ value, onChange }: { value: number; onChange: (x: number) => void }) {
  const set = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width) * 2 - 1));
    onChange(Math.abs(x) < 0.035 ? 0 : x); // the center mark catches
  };
  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label="sphere size"
      aria-valuemin={-1}
      aria-valuemax={1}
      aria-valuenow={Number(value.toFixed(2))}
      title="drag to contract or explode the sphere; double-click to reset"
      className="relative flex h-[18px] w-full cursor-ew-resize touch-none items-end justify-between"
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); set(e); }}
      onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) set(e); }}
      onDoubleClick={() => onChange(0)}
      onKeyDown={(e) => {
        const to = e.key === "ArrowLeft" ? value - 0.05 : e.key === "ArrowRight" ? value + 0.05 : e.key === "Home" ? 0 : null;
        if (to === null) return;
        e.preventDefault();
        e.stopPropagation(); // the arrows also turn the library's page
        onChange(Math.max(-1, Math.min(1, Math.abs(to) < 0.02 ? 0 : to)));
      }}
    >
      {Array.from({ length: TICKS }, (_, k) => {
        const x = k / MID - 1;
        const lit = k !== MID && (value > 0 ? x > 0 && x <= value + 1e-6 : x < 0 && x >= value - 1e-6);
        return (
          <span
            key={k}
            className={`w-px flex-none transition-colors duration-200 ${k === MID ? "h-[13px]" : k % 5 === 0 ? "h-[9px]" : "h-[5px]"} ${lit ? "bg-accent" : k === MID ? "bg-ink/80" : k % 5 === 0 ? "bg-ink/40" : "bg-ink/20"}`}
          />
        );
      })}
      <span className="pointer-events-none absolute bottom-0 h-full w-[1.5px] -translate-x-1/2 bg-accent" style={{ left: `${(value + 1) * 50}%` }}>
        <span className="absolute -top-[3px] left-1/2 size-[5px] -translate-x-1/2 rounded-full bg-accent" />
      </span>
    </div>
  );
}

/* The orb's own controls, top left: words set in the display face on a
   darkened corner, with brass marking whatever is on. */
export function OrbControls(p: Props) {
  const rowRef = useRef<HTMLDivElement>(null);
  const [rule, setRule] = useState<{ x: number; w: number } | null>(null);
  const [picking, setPicking] = useState(false);
  useLayoutEffect(() => {
    const el = rowRef.current?.querySelector<HTMLElement>(`[data-orb-lens="${p.layout}"]`);
    setRule(el ? { x: el.offsetLeft, w: el.offsetWidth } : null);
  }, [p.layout, p.settled]);
  const byCount = p.themes.map((t, th) => ({ ...t, th })).sort((a, b) => b.count - a.count);
  const pick = (th: number | null) => { p.onTheme(th); setPicking(false); };
  const stop = STOPS.reduce((b, s) => (Math.abs(s.at - p.spread) < Math.abs(b.at - p.spread) ? s : b));
  const item = (on: boolean) =>
    `${WORD} flex w-full items-baseline gap-3 rounded-[3px] px-2 py-[5px] text-left hover:bg-white/[0.06] ${on ? "text-ink" : "text-ink2 hover:text-ink"}`;
  return (
    <div
      className="absolute left-5 top-4 isolate flex w-[19rem] flex-col text-ink font-[540] tracking-[-0.015em]"
    >
      {/* the corner behind the words: darkened and out of focus, fading into the sky with no edge */}
      <div className="pointer-events-none absolute -left-5 -top-4 -z-10 h-[165%] w-[185%] bg-black/75 backdrop-blur-md [mask-image:radial-gradient(ellipse_at_0%_0%,#000_52%,transparent_74%)]" />
      <label className="flex items-baseline border-b border-ink/15 pb-1 transition-colors duration-200 focus-within:border-accent">
        <input
          ref={p.searchRef}
          type="search"
          data-orb-search
          value={p.query}
          placeholder="search the sphere"
          spellCheck={false}
          autoComplete="off"
          className="min-w-0 flex-1 appearance-none border-0 bg-transparent p-0 text-[16px] text-ink [font-weight:inherit] [letter-spacing:inherit] placeholder:italic placeholder:text-ink2/60 focus-visible:!outline-none [&::-webkit-search-cancel-button]:hidden"
          onChange={(e) => p.onQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") p.onEnter(); }}
        />
        {p.query ? null : <span className={`${SMALL} flex-none text-ink2/50`} title="press / to search">/</span>}
      </label>
      <div ref={rowRef} className="relative mt-3 flex items-baseline gap-5 pb-1.5 text-[22px] leading-none">
        {p.lenses.map(({ name, label, title }) => (
          <button key={name} type="button" data-orb-lens={name} title={title} className={word(p.layout === name)} onClick={() => p.onLayout(name)}>
            {label}
          </button>
        ))}
        {rule ? (
          <span
            className="pointer-events-none absolute bottom-0 left-0 h-[1.5px] bg-accent transition-[transform,width] duration-300 ease-hub"
            style={{ transform: `translateX(${rule.x}px)`, width: rule.w }}
          />
        ) : null}
      </div>
      <div className={`${SMALL} mt-3 flex items-baseline gap-4 leading-tight`}>
        <span className="flex items-baseline gap-2.5">
          {(["inside", "globe"] as const).map((v) => (
            <button key={v} type="button" data-orb-view={v} title={v === "inside" ? "stand at the center, tiles all around" : "step outside and look at the sphere"} className={sw(p.view === v)} onClick={() => p.onView(v)}>
              {v}
            </button>
          ))}
        </span>
        {p.view === "globe" ? (
          <button type="button" title="show the superplanet coastline under the tiles" className={`${sw(p.terrain)} starting:opacity-0 transition-opacity`} onClick={() => p.onTerrain(!p.terrain)}>
            terrain
          </button>
        ) : null}
        <button type="button" data-orb-library-toggle title="page through everything, in order" className={`${sw(p.library)} ml-auto`} onClick={p.onLibrary}>
          library <span className="text-[0.82em] tabular-nums text-accent">{p.count}</span>
        </button>
      </div>
      <div className={`${SMALL} mt-3.5 italic leading-none`}>
        <Scale value={p.spread} onChange={p.onSpread} />
        <div className="relative mt-1.5 h-[1.1em]">
          {STOPS.map((s) => (
            <button
              key={s.label}
              type="button"
              data-orb-stop={s.label}
              title={s.title}
              className={`${word(s === stop)} absolute top-0 ${s.at === -1 ? "" : s.at === 1 ? "-translate-x-full" : "-translate-x-1/2"}`}
              style={{ left: `${(s.at + 1) * 50}%` }}
              onClick={() => p.onSpread(s.at)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
      <Popover open={picking} onOpenChange={setPicking}>
        <PopoverTrigger asChild>
          <button type="button" data-orb-theme className={`${WORD} ${SMALL} mt-3.5 flex max-w-full items-baseline gap-2 self-start leading-tight ${p.theme === null ? "text-ink2/70 hover:text-ink" : "text-ink"}`}>
            <span className="truncate">{p.theme === null ? "all themes" : p.themes[p.theme]?.label.toLowerCase()}</span>
            <span className="flex-none text-[0.82em] tabular-nums text-accent">{p.theme === null ? p.count : p.themes[p.theme]?.count}</span>
            <span aria-hidden className={`flex-none text-[0.7em] text-ink2/60 transition-transform duration-200 ease-hub ${picking ? "rotate-180" : ""}`}>&#9662;</span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          sideOffset={8}
          className="w-[19rem] border-white/10 bg-black/85 p-1.5 backdrop-blur-md font-[540] tracking-[-0.015em] text-[13px] leading-tight"
        >
          <button type="button" className={item(p.theme === null)} onClick={() => pick(null)}>
            <span className="flex-1">all themes</span>
            <span className="text-[0.82em] tabular-nums text-accent">{p.count}</span>
          </button>
          {byCount.map((t) => (
            <button key={t.th} type="button" data-orb-theme-item={t.th} className={item(p.theme === t.th)} onClick={() => pick(t.th)}>
              <span className="min-w-0 flex-1 truncate">{t.label.toLowerCase()}</span>
              <span className="text-[0.82em] tabular-nums text-accent">{t.count}</span>
            </button>
          ))}
        </PopoverContent>
      </Popover>
    </div>
  );
}
