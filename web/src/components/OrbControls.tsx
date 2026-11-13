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
  waiting: number; // pending items not yet kept or dropped
  reading: boolean; // one of them is open
  onPending: () => void;
  dial: number; // the dial's position, in turns clockwise from the ring
  onDial: (c: number) => void;
  themes: { label: string; count: number }[];
  theme: number | null;
  onTheme: (th: number | null) => void;
};

// no preflight in the hub: a button keeps the browser's box unless each property is given back
export const WORD = "cursor-pointer appearance-none border-0 bg-transparent p-0 [font:inherit] [letter-spacing:inherit] transition-colors duration-200 ease-hub";
export const word = (on: boolean) => `${WORD} ${on ? "text-ink" : "text-ink2/60 hover:text-ink"}`;
// a switch that is on wears the brass rule the lens row slides
const sw = (on: boolean) => `${word(on)} border-b pb-px ${on ? "!border-accent" : "!border-transparent"}`;
const SMALL = "text-[13px]";

const TICKS = 40, DIAL = 92; // DIAL: css px across
// the shapes the pending items take around the dial, clockwise from the top; the last meets the first
const STOPS = [
  { at: 0, label: "ring", title: "the sphere at rest, the pending items in a ring", place: "bottom-full left-1/2 mb-2 -translate-x-1/2" },
  { at: 0.25, label: "atom", title: "the ring parted into three orbits", place: "left-full top-1/2 ml-2.5 -translate-y-1/2" },
  { at: 0.5, label: "coil", title: "the queue wound into one thread around the sphere, newest at the top", place: "top-full left-1/2 mt-2 -translate-x-1/2" },
  { at: 0.75, label: "dust", title: "the sphere drawn in, the pending items adrift around it", place: "right-full top-1/2 mr-2.5 -translate-y-1/2" },
];
// how far apart two places on the dial are, the short way around
const apart = (a: number, b: number) => { const d = Math.abs(a - b) % 1; return Math.min(d, 1 - d); };

/* The orb's states as a ruled dial: the ring at the top, then the orbits, the
   thread and the dust going clockwise, and the dust meets the ring again.
   Hand-built because a native range is a line and is drawn differently by
   every engine. */
function Dial({ value, onChange }: { value: number; onChange: (c: number) => void }) {
  const set = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    if (Math.hypot(dx, dy) < 6) return; // at the hub a bearing means nothing
    const c = (Math.atan2(dx, -dy) / (Math.PI * 2) + 1) % 1;
    onChange(apart(c, 0) < 0.015 ? 0 : c); // the ring's mark catches
  };
  const stop = STOPS.reduce((b, s) => (apart(s.at, value) < apart(b.at, value) ? s : b));
  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label="orb state"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={Number(value.toFixed(3))}
      aria-valuetext={stop.label}
      title="turn to take the pending items through their shapes; double-click to rest"
      className="size-full cursor-pointer touch-none rounded-full"
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); set(e); }}
      onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) set(e); }}
      onDoubleClick={() => onChange(0)}
      onKeyDown={(e) => {
        const to = e.key === "ArrowLeft" ? value - 1 / TICKS : e.key === "ArrowRight" ? value + 1 / TICKS : e.key === "Home" ? 0 : null;
        if (to === null) return;
        e.preventDefault();
        e.stopPropagation(); // the arrows also turn the library's page
        onChange(apart(to, 0) < 0.005 ? 0 : to);
      }}
    >
      <svg viewBox="-50 -50 100 100" className="block size-full overflow-visible" aria-hidden>
        {Array.from({ length: TICKS }, (_, k) => (
          <line
            key={k}
            x1={0}
            x2={0}
            y1={-45}
            y2={k % 10 === 0 ? -31 : k % 5 === 0 ? -36 : -40}
            transform={`rotate(${(k / TICKS) * 360})`}
            vectorEffect="non-scaling-stroke"
            strokeWidth={1}
            className={k % 10 === 0 ? "stroke-ink/80" : k % 5 === 0 ? "stroke-ink/40" : "stroke-ink/20"}
          />
        ))}
        <g transform={`rotate(${value * 360})`} className="fill-accent stroke-accent">
          <line x1={0} x2={0} y1={-27} y2={-49} vectorEffect="non-scaling-stroke" strokeWidth={1.5} />
          <circle cx={0} cy={-49} r={2.7} stroke="none" />
        </g>
      </svg>
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
  const stop = STOPS.reduce((b, s) => (apart(s.at, p.dial) < apart(b.at, p.dial) ? s : b));
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
      {/* the margins leave room for the two stop words above and below the dial */}
      <div className={`${SMALL} relative mx-auto mt-10 mb-7 italic leading-none`} style={{ width: DIAL, height: DIAL }}>
        <Dial value={p.dial} onChange={p.onDial} />
        {STOPS.map((s) => (
          <button key={s.label} type="button" data-orb-stop={s.label} title={s.title} className={`${word(s === stop)} absolute ${s.place}`} onClick={() => p.onDial(s.at)}>
            {s.label}
          </button>
        ))}
      </div>
      <Popover open={picking} onOpenChange={setPicking}>
        <div className={`${SMALL} flex items-baseline gap-4 leading-tight`}>
        <PopoverTrigger asChild>
          <button type="button" data-orb-theme className={`${WORD} flex min-w-0 items-baseline gap-2 ${p.theme === null ? "text-ink2/70 hover:text-ink" : "text-ink"}`}>
            <span className="truncate">{p.theme === null ? "all themes" : p.themes[p.theme]?.label.toLowerCase()}</span>
            <span className="flex-none text-[0.82em] tabular-nums text-accent">{p.theme === null ? p.count : p.themes[p.theme]?.count}</span>
            <span aria-hidden className={`flex-none text-[0.7em] text-ink2/60 transition-transform duration-200 ease-hub ${picking ? "rotate-180" : ""}`}>&#9662;</span>
          </button>
        </PopoverTrigger>
        {p.waiting > 0 ? (
          <button type="button" data-orb-inbox title="read the pending items, newest first" className={`${sw(p.reading)} ml-auto flex-none`} onClick={(e) => { e.currentTarget.blur(); p.onPending(); }}>
            pending <span className="text-[0.82em] tabular-nums text-accent">{p.waiting}</span>
          </button>
        ) : null}
        </div>
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
