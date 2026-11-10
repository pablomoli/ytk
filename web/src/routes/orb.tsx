import { useEffect, useMemo, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import type { LayoutName } from "../api/orb";
import { useOrb } from "../api/orb";
import { apiGet, queryClient } from "../api/client";
import type { SimilarItem } from "../api/fresh";
import { OrbReader, READER_WIDTH } from "../components/OrbReader";
import { ErrorState } from "../components/StateViews";
import type { OrbHandle, OrbViewMode } from "../lib/orb/scene";
import { mountOrb, RADIUS_MAX, RADIUS_MIN } from "../lib/orb/scene";
import { useChromeVisible } from "../lib/chrome";
import { validateOrbSearch } from "../lib/orbSearch";
import "../styles.css";

// same queryKey/queryFn shape as useNote/useSimilarNotes (api/fresh.ts) so the
// warmed cache entry is the exact one those hooks read on open
function prefetchNote(path: string): void {
  void queryClient.prefetchQuery({
    queryKey: ["note", path],
    queryFn: () =>
      apiGet<{ path: string; content: string }>(
        `/api/note?path=${encodeURIComponent(path)}`,
      ),
  });
  void queryClient.prefetchQuery({
    queryKey: ["similar", path],
    queryFn: () =>
      apiGet<SimilarItem[]>(
        `/api/similar?note=${encodeURIComponent(path)}&n=8`,
      ),
  });
}

export const Route = createFileRoute("/orb")({
  component: OrbPage,
  validateSearch: validateOrbSearch,
});

// lenses: the same tiles, three arrangements, named for what you see
const LENSES: { name: LayoutName; label: string; hint: string }[] = [
  { name: "radial", label: "neighbors", hint: "tiles sit by embedding neighborhood" },
  { name: "lattice", label: "themes", hint: "tiles grouped in theme blocks" },
  { name: "time", label: "time", hint: "newest at the top of the sphere, oldest at the bottom" },
];

// build_map sometimes emits raw Obsidian embed syntax in titles; strip for display only
const captionTitle = (t: string) =>
  t.replace(/!\[\[([^\]]+)\]\]/g, "$1").trim();

// mean direction of a theme's tiles under the chosen sphere layout; null when
// the theme has no tiles or they cancel out
function themeCentroid(
  data: NonNullable<ReturnType<typeof useOrb>["data"]>,
  th: number,
): [number, number, number] | null {
  const pos = data.sphere[data.sphere.chosen] ?? data.sphere.radial;
  if (!pos) return null;
  const acc: [number, number, number] = [0, 0, 0];
  let n = 0;
  const len = Math.min(pos.length, data.points.length);
  for (let i = 0; i < len; i++) {
    if (data.points[i].th !== th) continue;
    acc[0] += pos[i][0];
    acc[1] += pos[i][1];
    acc[2] += pos[i][2];
    n++;
  }
  if (n === 0) return null;
  const l = Math.hypot(acc[0], acc[1], acc[2]);
  return l < 1e-9 ? null : [acc[0] / l, acc[1] / l, acc[2] / l];
}

function OrbPage() {
  const chrome = useChromeVisible();
  const orb = useOrb();
  const searchTheme = Route.useSearch().theme;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handleRef = useRef<OrbHandle | null>(null);
  const [layout, setLayout] = useState<LayoutName | null>(null);
  const [viewMode, setViewMode] = useState<OrbViewMode>("inside");
  const [theme, setTheme] = useState<number | null>(null);
  const [terrain, setTerrain] = useState(false);
  // slider position: 0 is the unit sphere, the ends are the radius limits, log-spaced
  const [spread, setSpread] = useState(0);
  const applySpread = (x: number) => {
    setSpread(x);
    handleRef.current?.setRadius(x < 0 ? Math.pow(RADIUS_MIN, -x) : Math.pow(RADIUS_MAX, x));
  };
  const [hovered, setHovered] = useState<number | null>(null);
  // the neighbors panel anchors on the last hovered tile and stays put, so the
  // pointer can leave the sphere to read or click the list
  const [anchor, setAnchor] = useState<number | null>(null);
  // selected: the tile the sphere is parked on. reader: the pane's note, which
  // outlives the selection by one slide-out so closing has somewhere to go
  const [selected, setSelected] = useState<number | null>(null);
  const [reader, setReader] = useState<number | null>(null);
  const selectedRef = useRef<number | null>(null); // read inside the scene callbacks, which close over the first render
  selectedRef.current = selected;
  const data = orb.data;
  const pathIndex = useMemo(() => new Map((data?.points ?? []).map((p, i) => [p.p, i] as const)), [data]);
  const urlIndex = useMemo(
    () => new Map((data?.points ?? []).flatMap((p, i) => (p.u ? [[p.u, i] as const] : []))),
    [data],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      handleRef.current?.blur();
      setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const handle = mountOrb(canvas, data, {
      onHover: (i) => {
        setHovered(i);
        if (i !== null) {
          if (selectedRef.current === null) setAnchor(i); // while selected the panel belongs to the selection
          prefetchNote(data.points[i].p);
        }
      },
      onOpen: (i) => { setSelected(i); setReader(i); setAnchor(i); },
      onBlur: () => setSelected(null),
    });
    handleRef.current = handle;
    handle.setDock(READER_WIDTH);
    // spike defaults: lattice on, terrain off, inside
    handle.setLayout("lattice");
    setLayout("lattice");
    setViewMode("inside"); // matches the freshly mounted handle's initial mode
    setTerrain(false); // ... and its initial terrain flag
    setSpread(0); // ... and its unit radius
    // ?theme= deep-link from /galaxy's "land" button: apply to the freshly
    // mounted handle, not just state, so a fresh navigation lands filtered
    if (searchTheme !== undefined) {
      setTheme(searchTheme);
      handle.setThemeFilter(searchTheme);
      // the theme's tiles can sit behind the default camera, which lands the
      // user facing nothing but dimmed ones; open pointed at their centroid
      const dir = themeCentroid(data, searchTheme);
      if (dir) handle.aimAt(dir);
    }
    return () => {
      handleRef.current = null;
      handle.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (orb.isError)
    return <ErrorState error={orb.error} onRetry={() => void orb.refetch()} />;

  const scores = data?.sphere.scores;
  const knn = data?.sphere.knn;
  const knnSim = data?.sphere.knn_sim;
  // from the panel or the pane: while a tile is selected a step selects the
  // next one (camera walks, pane swaps); otherwise it only turns the sphere
  const walkTo = (j: number) => {
    const h = handleRef.current;
    if (!h) return;
    if (selected !== null) h.focus(j);
    else { setAnchor(j); h.aimAt(h.centerOf(j)); }
  };
  const closeReader = () => {
    handleRef.current?.blur();
    setSelected(null);
  };
  return (
    <div className="relative flex-1 min-h-0 overflow-hidden">
      {!data ? (
        <div className="flex-1 grid place-items-center text-sm opacity-60">
          loading the sphere
        </div>
      ) : (
        <canvas
          ref={canvasRef}
          className={`h-full w-full ${hovered !== null ? "cursor-pointer" : "cursor-grab active:cursor-grabbing"}`}
        />
      )}
      {data && chrome ? (
        <div className="absolute left-4 top-4 flex flex-col gap-2 text-xs">
          <div className="flex gap-1">
            {LENSES.map(({ name, label, hint }) => {
              const s = scores?.[name];
              return (
                <button
                  key={name}
                  type="button"
                  title={s ? `${hint} · trust ${s.trustworthiness.toFixed(3)}` : hint}
                  className={`rounded px-2 py-1 ${layout === name ? "bg-white/20" : "bg-white/5 hover:bg-white/10"} disabled:opacity-30`}
                  onClick={() => {
                    setLayout(name);
                    handleRef.current?.setLayout(name);
                  }}
                >
                  {label}
                </button>
              );
            })}
            <button
              type="button"
              className="ml-2 rounded px-2 py-1 bg-white/5 hover:bg-white/10"
              onClick={() => {
                const next: OrbViewMode =
                  viewMode === "inside" ? "globe" : "inside";
                setViewMode(next);
                handleRef.current?.setView(next);
              }}
            >
              {viewMode === "inside" ? "globe" : "inside"}
            </button>
            <button
              type="button"
              disabled={viewMode !== "globe"}
              title="show the superplanet coastline under the tiles"
              className={`rounded px-2 py-1 ${terrain ? "bg-white/20" : "bg-white/5 hover:bg-white/10"} disabled:opacity-30`}
              onClick={() => {
                const next = !terrain;
                setTerrain(next);
                handleRef.current?.setTerrain(next);
              }}
            >
              terrain
            </button>
          </div>
          <label className="flex items-center gap-2 text-[11px] text-[var(--ink2)]" title="double-click to reset">
            <span>contract</span>
            <input
              type="range"
              min={-1}
              max={1}
              step={0.005}
              value={spread}
              className="h-1 min-w-0 flex-1 cursor-pointer accent-[var(--ink2)]"
              onChange={(e) => applySpread(Number(e.target.value))}
              onDoubleClick={() => applySpread(0)}
            />
            <span>explode</span>
          </label>
          <select
            className="rounded bg-white/5 px-2 py-1"
            value={theme ?? ""}
            onChange={(e) => {
              const v = e.target.value === "" ? null : Number(e.target.value);
              setTheme(v);
              handleRef.current?.setThemeFilter(v);
            }}
          >
            <option value="">all themes</option>
            {data.themes.map((label, i) => (
              <option key={label} value={i}>
                {label}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {data && chrome && anchor !== null && knn ? (
        <aside className="absolute bottom-4 left-4 w-80 overflow-hidden rounded-lg border border-white/10 bg-black/70 shadow-2xl backdrop-blur-md">
          <div className="border-b border-white/10 px-4 pt-3 pb-2.5">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--ink2)]">nearest by embedding</div>
            <div className="mt-1 truncate text-[15px] leading-tight text-[var(--ink)]">{captionTitle(data.points[anchor].t)}</div>
          </div>
          <div className="relative">
            {/* exactly five rows tall; the rest scrolls */}
            <ul className="!m-0 h-[300px] !list-none overflow-y-auto !p-0 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.18)_transparent]">
              {(knn[anchor] ?? []).map((j, k) => {
                const q = data.points[j];
                const sim = knnSim?.[anchor]?.[k];
                return (
                  <li key={j} className="!m-0 !list-none border-b border-white/[0.06] !p-0 last:border-b-0">
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => walkTo(j)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); walkTo(j); } }}
                      className="flex h-[60px] cursor-pointer items-center gap-3 px-4 transition-colors hover:bg-white/[0.06] focus:outline-none focus-visible:bg-white/[0.06]"
                    >
                      {q.thumb ? (
                        <span className="flex h-11 w-11 flex-none items-center justify-center">
                          {/* whole cover inside the box, shape kept: a reel is tall here, a video is wide */}
                          <img src={`/vault-media/${q.thumb}`} alt="" className="max-h-11 max-w-11 rounded-[3px] object-contain" />
                        </span>
                      ) : (
                        <span className="h-11 w-11 flex-none rounded-[3px] bg-white/[0.06]" />
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="line-clamp-2 text-[13px] leading-[1.25] text-[var(--ink)]">{captionTitle(q.t)}</span>
                        <span className="mt-0.5 block truncate text-[10.5px] uppercase tracking-[0.08em] text-[var(--ink2)]">
                          {q.c}{q.d ? ` · ${q.d}` : ""}
                        </span>
                      </span>
                      {sim !== undefined ? (
                        <span className="flex-none text-[12px] tabular-nums text-[var(--accent)]">{Math.round(sim * 100)}</span>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-black/60 to-transparent" />
          </div>
        </aside>
      ) : null}
      {data && hovered !== null && hovered !== selected ? (
        <div
          data-caption
          className="pointer-events-none absolute bottom-4 -translate-x-1/2 rounded bg-black/60 px-3 py-1 text-sm"
          style={{ left: selected !== null ? `calc(50% - ${READER_WIDTH / 2}px)` : "50%" }}
        >
          {captionTitle(data.points[hovered].t)}
          {data.points[hovered].d ? (
            <span className="ml-2 opacity-60">{data.points[hovered].d}</span>
          ) : null}
        </div>
      ) : null}
      {data && reader !== null ? (
        <OrbReader
          point={data.points[reader]}
          open={selected !== null}
          pathIndex={pathIndex}
          urlIndex={urlIndex}
          onWalk={walkTo}
          onClose={closeReader}
          onGone={() => setReader(null)}
        />
      ) : null}
    </div>
  );
}
