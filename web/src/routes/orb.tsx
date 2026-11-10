import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import type { LayoutName, OrbPoint } from "../api/orb";
import { useOrb } from "../api/orb";
import { apiGet, queryClient } from "../api/client";
import type { SimilarItem } from "../api/fresh";
import type { LibraryPage } from "../api/library";
import { OrbControls } from "../components/OrbControls";
import { OrbReader, READER_WIDTH } from "../components/OrbReader";
import { ErrorState } from "../components/StateViews";
import type { OrbHandle, OrbViewMode } from "../lib/orb/scene";
import type { RingItem } from "../lib/orb/ring";
import { mountOrb, RADIUS_MAX, RADIUS_MIN, SHELF_COLS_MAX, SHELF_FILL, SHELF_ROWS } from "../lib/orb/scene";
import type { SheetTile } from "../lib/orb/scene";
import { faceStack, faceVars, loadFace } from "../lib/orb/faces";
import type { FaceName } from "../lib/orbSearch";
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

type SearchHit = { i: number; s: number };

// library orders: the first two follow the library's own list, newest added first
const SORTS = [
  { name: "newest", label: "newest" },
  { name: "oldest", label: "oldest" },
  { name: "published", label: "published" },
  { name: "title", label: "title" },
] as const;
type SortName = (typeof SORTS)[number]["name"];
// set in the orb's display face, which the page root carries as custom properties
const FACE = "[font-family:var(--face)] [font-variation-settings:var(--face-vary)] [font-weight:var(--face-w)] [letter-spacing:var(--face-track)]";
const PANEL_RIGHT = 344; // css px the bottom-left panel reaches to; the sheet starts past it at least
const CHIP = "cursor-pointer rounded px-2 py-1";
const chip = (on: boolean) => `${CHIP} ${on ? "bg-white/20 text-[var(--ink)]" : "bg-white/5 hover:bg-white/10"}`;

// one row of the bottom-left panel: a tile's cover, title, creator and date, and a brass score
function TileRow({ point, score, when, active, onPick }: { point: OrbPoint; score?: number | undefined; when?: string | undefined; active?: boolean; onPick: () => void }) {
  return (
    <li className="!m-0 !list-none border-b border-white/[0.06] !p-0 last:border-b-0">
      <div
        role="button"
        tabIndex={0}
        onClick={onPick}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(); } }}
        className={`flex h-[60px] cursor-pointer items-center gap-3 px-4 transition-colors hover:bg-white/[0.06] focus:outline-none focus-visible:bg-white/[0.06] ${active ? "bg-white/[0.08]" : ""}`}
      >
        {point.thumb ? (
          <span className="flex h-11 w-11 flex-none items-center justify-center">
            {/* whole cover inside the box, shape kept: a reel is tall here, a video is wide */}
            <img src={`/vault-media/${point.thumb}`} alt="" className="max-h-11 max-w-11 rounded-[3px] object-contain" />
          </span>
        ) : (
          <span className="h-11 w-11 flex-none rounded-[3px] bg-white/[0.06]" />
        )}
        <span className="min-w-0 flex-1">
          <span className={`${FACE} line-clamp-2 text-[calc(12.5px*var(--face-k))] leading-[1.15] text-[var(--ink)]`}>{captionTitle(point.t)}</span>
          <span className="mt-0.5 block truncate text-[10.5px] uppercase tracking-[0.08em] text-[var(--ink2)]">
            {point.c}{when ?? point.d ? ` · ${when ?? point.d}` : ""}
          </span>
        </span>
        {score !== undefined ? (
          <span className="flex-none text-[12px] tabular-nums text-[var(--accent)]">{Math.round(score * 100)}</span>
        ) : null}
      </div>
    </li>
  );
}

// the bottom-left panel's header; while a tile is read it is the handle the folded list opens from
function PanelHead({ label, title, folded, onToggle }: { label: string; title: string; folded: boolean; onToggle: (() => void) | undefined }) {
  const kicker = "text-[10px] uppercase tracking-[0.18em] text-[var(--ink2)]";
  return (
    <div
      role={onToggle ? "button" : undefined}
      tabIndex={onToggle ? 0 : undefined}
      onClick={onToggle}
      className={`${folded ? "flex items-baseline gap-3 px-3 py-2" : "border-b border-white/10 px-4 pt-3 pb-2.5"} ${onToggle ? "cursor-pointer hover:bg-white/[0.06]" : ""}`}
    >
      {folded ? (
        <>
          <span className={`${kicker} flex-none`}>{label}</span>
          <span className={`${FACE} min-w-0 flex-1 truncate text-[calc(13.5px*var(--face-k))] leading-tight text-[var(--ink)]`}>{title}</span>
          <span className={`${kicker} flex-none`}>show</span>
        </>
      ) : (
        <>
          <div className={`${kicker} flex items-baseline`}>
            <span className="flex-1">{label}</span>
            {onToggle ? <span>hide</span> : null}
          </div>
          <div className={`${FACE} mt-1 truncate text-[calc(16px*var(--face-k))] leading-tight text-[var(--ink)]`}>{title}</div>
        </>
      )}
    </div>
  );
}

/* One cover's title, set on the cover's darkened foot. The scene owns where
   the cover is; this only sets words against the rectangle it reports. The
   shade is as tall as the words, so under the pointer both open together. */
function SheetTitle({ at, point, lit }: { at: SheetTile; point: OrbPoint; lit: boolean }) {
  // a reel's narrow cover and a video's wide one both hold about four words a line
  const px = Math.max(11.5, Math.min(16, at.w * 0.085));
  const pad = `${(at.w * 0.06).toFixed(1)}px`;
  return (
    <div
      data-sheet-title
      className="pointer-events-none absolute left-0 top-0 flex items-end overflow-hidden transition-opacity duration-300 starting:opacity-0"
      style={{ transform: `translate(${at.cx - at.w / 2}px, ${at.top}px)`, width: at.w, height: at.bottom - at.top }}
    >
      <div
        className="box-border w-full bg-gradient-to-t from-black/90 via-black/80 via-65% to-transparent [text-shadow:0_0_2px_#000,0_0_8px_rgb(0_0_0/0.8)]"
        style={{ padding: `${(px * 2.2).toFixed(1)}px ${pad} ${(at.w * 0.045).toFixed(1)}px` }}
      >
        <span
          className={`${FACE} leading-[1.12] text-[var(--ink)] ${lit ? "line-clamp-5" : "line-clamp-2"}`}
          style={{ fontSize: `calc(${px.toFixed(1)}px * var(--face-k))` }}
        >
          {captionTitle(point.t)}
        </span>
      </div>
    </div>
  );
}

function OrbPage() {
  const chrome = useChromeVisible();
  const orb = useOrb();
  const { theme: searchTheme, face = "instrument" } = Route.useSearch();
  // the scene draws its labels into canvases, so it mounts once the face can be drawn
  const [drawn, setDrawn] = useState<FaceName | null>(null);
  useEffect(() => {
    let live = true;
    void loadFace(face).then(() => { if (live) setDrawn(face); });
    return () => { live = false; };
  }, [face]);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handleRef = useRef<OrbHandle | null>(null);
  const [layout, setLayout] = useState<LayoutName | null>(null);
  const [viewMode, setViewMode] = useState<OrbViewMode>("inside");
  const [theme, setTheme] = useState<number | null>(null);
  const [terrain, setTerrain] = useState(false);
  // slider position: 0 is the sphere at the size its tile count gives it, the ends are the radius limits, log-spaced
  const [spread, setSpread] = useState(0);
  const applySpread = (x: number) => {
    setSpread(x);
    handleRef.current?.setRadius(x < 0 ? Math.pow(RADIUS_MIN, -x) : Math.pow(RADIUS_MAX, x));
  };
  const [hovered, setHovered] = useState<number | null>(null);
  const [grain, setGrain] = useState<RingItem | null>(null); // the pending item under the pointer
  const [sheetTiles, setSheetTiles] = useState<SheetTile[]>([]); // the sheet's landed covers, from the scene
  // the neighbors panel anchors on the last hovered tile and stays put, so the
  // pointer can leave the sphere to read or click the list
  const [anchor, setAnchor] = useState<number | null>(null);
  // selected: the tile the sphere is parked on. reader: the pane's note, which
  // outlives the selection by one slide-out so closing has somewhere to go
  const [selected, setSelected] = useState<number | null>(null);
  const [reader, setReader] = useState<number | null>(null);
  const selectedRef = useRef<number | null>(null); // read inside the scene callbacks, which close over the first render
  // while a tile is read the bottom-left list folds under its header, so the tile has the sky to itself
  const [listOpen, setListOpen] = useState(false);
  selectedRef.current = selected;
  // search: the matches gather in front of the camera and replace the neighbors in the panel
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searchState, setSearchState] = useState<"idle" | "busy" | "failed">("idle");
  const searchRef = useRef<HTMLInputElement>(null);
  const queryRef = useRef("");
  queryRef.current = query;
  // library: the whole collection in a chosen order, a page at a time on the sheet search uses
  const [library, setLibrary] = useState(false);
  const [source, setSource] = useState<string | null>(null);
  const [sort, setSort] = useState<SortName>("newest");
  const [page, setPage] = useState(0);
  const [cols, setCols] = useState(6);
  // tiles carry no date added; the library's own list does, and its order is that date
  const shelf = useQuery({
    queryKey: ["library", "all"],
    queryFn: () => apiGet<LibraryPage>("/api/library?n=5000"),
    staleTime: 60_000,
  });
  const data = orb.data;
  const pathIndex = useMemo(() => new Map((data?.points ?? []).map((p, i) => [p.p, i] as const)), [data]);
  const urlIndex = useMemo(
    () => new Map((data?.points ?? []).flatMap((p, i) => (p.u ? [[p.u, i] as const] : []))),
    [data],
  );

  // each library note's place in the library's list, and the day it was added
  const shelfIndex = useMemo(
    () => new Map((shelf.data?.items ?? []).map((it, k) => [it.path, { k, added: it.added }] as const)),
    [shelf.data],
  );
  // the library's order over the tiles the filters keep
  const order = useMemo(() => {
    if (!data) return [];
    const pts = data.points;
    const keep = pts.map((_, i) => i).filter((i) => (source === null || pts[i].c === source) && (theme === null || pts[i].th === theme));
    const byDate = (a: number, b: number) => (pts[b].d ?? "").localeCompare(pts[a].d ?? "");
    // until the library's list arrives, its two orders fall back to the publish date
    const byAdded = (a: number, b: number) => (shelfIndex.get(pts[a].p)?.k ?? 1e9) - (shelfIndex.get(pts[b].p)?.k ?? 1e9) || byDate(a, b);
    if (sort === "title") return keep.sort((a, b) => captionTitle(pts[a].t).localeCompare(captionTitle(pts[b].t)));
    if (sort === "published") return keep.sort(byDate);
    return sort === "newest" ? keep.sort(byAdded) : keep.sort((a, b) => byAdded(b, a));
  }, [data, shelfIndex, source, theme, sort]);
  const pageSize = cols * SHELF_ROWS;
  const pages = Math.max(1, Math.ceil(order.length / pageSize));
  const at = Math.min(page, pages - 1);
  const pageItems = useMemo(() => order.slice(at * pageSize, (at + 1) * pageSize), [order, at, pageSize]);
  const turn = (by: number) => setPage(Math.max(0, Math.min(pages - 1, at + by)));
  const live = useRef({ library, turn });
  live.current = { library, turn };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return; // an open theme list takes its own Escape
      const el = e.target as HTMLElement | null;
      const typing = el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
        return;
      }
      // the arrows turn the library's page while nothing is read or searched
      if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && !typing && live.current.library && selectedRef.current === null && !queryRef.current) {
        e.preventDefault();
        live.current.turn(e.key === "ArrowRight" ? 1 : -1);
        return;
      }
      if (e.key !== "Escape") return;
      // one layer per press: the reader closes first, then the search clears, then the library
      if (selectedRef.current !== null) {
        handleRef.current?.blur();
        setSelected(null);
        return;
      }
      if (queryRef.current) {
        setQuery("");
        searchRef.current?.blur();
        return;
      }
      setLibrary(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setHits(null);
      setSearchState("idle");
      return;
    }
    setSearchState("busy");
    const ctl = new AbortController();
    // one request per pause in typing; the next keystroke cancels this one
    const timer = window.setTimeout(() => {
      fetch(`/api/orb-search?q=${encodeURIComponent(q)}&n=12`, { signal: ctl.signal })
        .then((r) => (r.ok ? (r.json() as Promise<{ hits: SearchHit[] }>) : Promise.reject(new Error(String(r.status)))))
        .then((d) => {
          setHits(d.hits);
          setSearchState("idle");
        })
        .catch(() => {
          if (ctl.signal.aborted) return;
          setHits([]);
          setSearchState("failed");
        });
    }, 250);
    return () => {
      window.clearTimeout(timer);
      ctl.abort();
    };
  }, [query]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data || drawn !== face) return;
    const handle = mountOrb(canvas, data, {
      onHover: (i) => {
        setHovered(i);
        if (i !== null) {
          if (selectedRef.current === null) setAnchor(i); // while selected the panel belongs to the selection
          prefetchNote(data.points[i].p);
        }
      },
      onOpen: (i) => { setSelected(i); setReader(i); setAnchor(i); setListOpen(false); },
      onBlur: () => setSelected(null),
      onRingHover: setGrain,
      onSheet: setSheetTiles,
    }, faceStack(face));
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
  }, [data, drawn]);

  // css px from the canvas's left edge to the right edge of the top-left controls
  const fieldRight = () =>
    Math.max(0, (searchRef.current?.getBoundingClientRect().right ?? 0) - (canvasRef.current?.getBoundingClientRect().left ?? 0));
  // the sheet has one owner: a search's matches, else the library's page, else nothing.
  // Declared after the mount so a fresh handle gets the current set
  const searching = query.trim() !== "";
  useEffect(() => {
    const h = handleRef.current;
    if (!h) return;
    if (searching) {
      // the sheet keeps clear of the left column of panels, which the field shares an edge with
      if (hits) h.setSearch(hits.map((x) => x.i), fieldRight()); // a pending search leaves the sheet as it is
    } else if (library) h.setSearch(pageItems, Math.max(PANEL_RIGHT, fieldRight() + 12), { cols, rows: SHELF_ROWS, fill: SHELF_FILL });
    else h.setSearch(null);
  }, [data, drawn, searching, hits, library, pageItems, cols]);

  // as many columns as the sky beside the panel holds at the sheet's slot size
  useEffect(() => {
    if (!library) return;
    const fit = () => {
      const c = canvasRef.current;
      if (!c) return;
      const slot = (SHELF_FILL * c.clientHeight) / SHELF_ROWS;
      setCols(Math.max(3, Math.min(SHELF_COLS_MAX, Math.floor((c.clientWidth - Math.max(PANEL_RIGHT, fieldRight() + 12)) / slot))));
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [library]);

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
  const folded = selected !== null && !listOpen;
  // source chips count the tiles the theme filter keeps
  const sourceCounts = new Map<string, number>();
  let themed = 0;
  for (const p of data?.points ?? []) {
    if (theme !== null && p.th !== theme) continue;
    themed++;
    sourceCounts.set(p.c, (sourceCounts.get(p.c) ?? 0) + 1);
  }
  // under the library's own orders a row shows the day its note was added, which is what placed it
  const added = (i: number) => {
    const day = data ? shelfIndex.get(data.points[i].p)?.added : undefined;
    return day ? `added ${day}` : undefined;
  };
  // library notes with no tile: the sphere is a snapshot and the library is live
  const unplaced = shelf.data ? shelf.data.items.filter((it) => !pathIndex.has(it.path)).length : 0;
  const themeCounts = (data?.themes ?? []).map((label) => ({ label, count: 0 }));
  for (const p of data?.points ?? []) if (themeCounts[p.th]) themeCounts[p.th].count++;
  const closeReader = () => {
    handleRef.current?.blur();
    setSelected(null);
  };
  return (
    <div className="relative flex-1 min-h-0 overflow-hidden" style={faceVars(face)}>
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
        <OrbControls
          searchRef={searchRef}
          face={faceVars(face)}
          settled={drawn}
          query={query}
          onQuery={setQuery}
          onEnter={() => { if (hits?.length) handleRef.current?.focus(hits[0].i); }} // Enter takes the best match
          lenses={LENSES.map(({ name, label, hint }) => {
            const s = scores?.[name];
            return { name, label, title: s ? `${hint} · trust ${s.trustworthiness.toFixed(3)}` : hint };
          })}
          layout={layout}
          onLayout={(name) => { setLayout(name); handleRef.current?.setLayout(name); }}
          view={viewMode}
          onView={(next) => { setViewMode(next); handleRef.current?.setView(next); }}
          terrain={terrain}
          onTerrain={(next) => { setTerrain(next); handleRef.current?.setTerrain(next); }}
          library={library}
          count={data.points.length}
          onLibrary={() => { setLibrary((v) => !v); setPage(0); }}
          spread={spread}
          onSpread={applySpread}
          themes={themeCounts}
          theme={theme}
          onTheme={(v) => { setTheme(v); setPage(0); handleRef.current?.setThemeFilter(v); }}
        />
      ) : null}
      {data && chrome && query.trim() ? (
        <aside data-orb-results className={`absolute bottom-4 left-4 overflow-hidden rounded-lg border border-white/10 bg-black/70 shadow-2xl backdrop-blur-md ${folded ? "max-w-80" : "w-80"}`}>
          <PanelHead
            label={searchState === "busy" ? "searching" : searchState === "failed" ? "search did not answer" : `${hits?.length ?? 0} closest by meaning`}
            title={query.trim()}
            folded={folded}
            onToggle={selected !== null ? () => setListOpen((v) => !v) : undefined}
          />
          {!folded && hits?.length ? (
            <div className="relative">
              <ul className="!m-0 max-h-[420px] !list-none overflow-y-auto !p-0 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.18)_transparent]">
                {hits.map((h) => (
                  <TileRow
                    key={h.i}
                    point={data.points[h.i]}
                    score={h.s}
                    active={h.i === selected || h.i === hovered}
                    onPick={() => handleRef.current?.focus(h.i)}
                  />
                ))}
              </ul>
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-black/60 to-transparent" />
            </div>
          ) : null}
        </aside>
      ) : data && chrome && library ? (
        <aside data-orb-library className={`absolute bottom-4 left-4 overflow-hidden rounded-lg border border-white/10 bg-black/70 shadow-2xl backdrop-blur-md ${folded ? "max-w-80" : "w-80"}`}>
          <PanelHead
            label={`library · page ${at + 1} of ${pages}`}
            title={`${order.length} ${source ?? "notes"}${theme !== null ? ` in ${data.themes[theme]}` : ""}, ${sort === "title" ? "by title" : sort === "published" ? "by publish date" : `${sort} first`}`}
            folded={folded}
            onToggle={selected !== null ? () => setListOpen((v) => !v) : undefined}
          />
          {!folded ? (
            <>
              <div className="flex flex-wrap gap-1 border-b border-white/10 px-3 py-2 text-[11px] text-[var(--ink2)]">
                <span role="button" tabIndex={0} className={chip(source === null)} onClick={() => { setSource(null); setPage(0); }}>
                  all {themed}
                </span>
                {[...sourceCounts].sort((a, b) => b[1] - a[1]).map(([name, count]) => (
                  <span key={name} role="button" tabIndex={0} className={chip(source === name)} onClick={() => { setSource(name); setPage(0); }}>
                    {name} {count}
                  </span>
                ))}
              </div>
              <div className="flex gap-1 border-b border-white/10 px-3 py-2 text-[11px] text-[var(--ink2)]">
                {SORTS.map(({ name, label }) => (
                  <span key={name} role="button" tabIndex={0} className={chip(sort === name)} onClick={() => { setSort(name); setPage(0); }}>
                    {label}
                  </span>
                ))}
              </div>
              <div className="flex items-center border-b border-white/10 px-3 py-1.5 text-[11px] text-[var(--ink2)]">
                <span role="button" tabIndex={0} data-orb-page="-1" className={`${CHIP} hover:bg-white/10 ${at === 0 ? "pointer-events-none opacity-30" : ""}`} onClick={() => turn(-1)}>
                  previous
                </span>
                <span className="flex-1 text-center tabular-nums">
                  {order.length ? `${at * pageSize + 1} to ${Math.min(order.length, (at + 1) * pageSize)} of ${order.length}` : "nothing here"}
                </span>
                <span role="button" tabIndex={0} data-orb-page="1" className={`${CHIP} hover:bg-white/10 ${at >= pages - 1 ? "pointer-events-none opacity-30" : ""}`} onClick={() => turn(1)}>
                  next
                </span>
              </div>
              <div className="relative">
                <ul className="!m-0 h-[240px] !list-none overflow-y-auto !p-0 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.18)_transparent]">
                  {pageItems.map((i) => (
                    <TileRow
                      key={i}
                      point={data.points[i]}
                      when={sort === "newest" || sort === "oldest" ? added(i) : undefined}
                      active={i === selected || i === hovered}
                      onPick={() => handleRef.current?.focus(i)}
                    />
                  ))}
                </ul>
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-black/60 to-transparent" />
              </div>
              {shelf.isError ? (
                <div className="border-t border-white/10 px-4 py-2 text-[10.5px] text-[var(--ink2)]">the library's list did not load: newest and oldest follow the publish date</div>
              ) : unplaced ? (
                <div data-orb-unplaced className="border-t border-white/10 px-4 py-2 text-[10.5px] text-[var(--ink2)]">{unplaced} library notes have no tile on the sphere yet</div>
              ) : null}
            </>
          ) : null}
        </aside>
      ) : data && chrome && anchor !== null && knn ? (
        <aside data-orb-neighbors className={`absolute bottom-4 left-4 overflow-hidden rounded-lg border border-white/10 bg-black/70 shadow-2xl backdrop-blur-md ${folded ? "max-w-80" : "w-80"}`}>
          <PanelHead
            label="nearest by embedding"
            title={captionTitle(data.points[anchor].t)}
            folded={folded}
            onToggle={selected !== null ? () => setListOpen((v) => !v) : undefined}
          />
          <div className={`relative ${folded ? "hidden" : ""}`}>
            {/* exactly five rows tall; the rest scrolls */}
            <ul className="!m-0 h-[300px] !list-none overflow-y-auto !p-0 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.18)_transparent]">
              {(knn[anchor] ?? []).map((j, k) => (
                <TileRow key={j} point={data.points[j]} score={knnSim?.[anchor]?.[k]} onPick={() => walkTo(j)} />
              ))}
            </ul>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-black/60 to-transparent" />
          </div>
        </aside>
      ) : null}
      {data ? sheetTiles.map((at) => <SheetTitle key={at.i} at={at} point={data.points[at.i]} lit={at.i === hovered} />) : null}
      {data && hovered !== null && hovered !== selected && !sheetTiles.some((at) => at.i === hovered) ? (
        <div
          data-caption
          className={`${FACE} pointer-events-none absolute bottom-4 -translate-x-1/2 rounded bg-black/60 px-3 py-1 text-[calc(15px*var(--face-k))]`}
          style={{ left: selected !== null ? `calc(50% - ${READER_WIDTH / 2}px)` : "50%" }}
        >
          {captionTitle(data.points[hovered].t)}
          {data.points[hovered].d ? (
            <span className="ml-2 opacity-60">{data.points[hovered].d}</span>
          ) : null}
        </div>
      ) : null}
      {data && grain ? (
        <div
          data-ring-caption
          className="pointer-events-none absolute bottom-4 left-1/2 flex w-[26rem] -translate-x-1/2 items-center gap-3 rounded-lg border border-white/10 bg-black/70 px-3 py-2.5 shadow-2xl backdrop-blur-md"
        >
          {/* only cached covers: asking for an uncached one makes the hub download it */}
          {grain.k >= 0 ? (
            <span className="flex h-14 w-14 flex-none items-center justify-center">
              <img src={`/api/cover?u=${encodeURIComponent(grain.u)}`} alt="" className="max-h-14 max-w-14 rounded-[3px] object-contain" />
            </span>
          ) : null}
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] uppercase tracking-[0.18em] text-[var(--ink2)]">
              pending
              {grain.q ? <span className="ml-2 text-[var(--accent)]">open question</span> : null}
            </span>
            <span className={`${FACE} mt-0.5 line-clamp-2 text-[calc(13.5px*var(--face-k))] leading-[1.22] text-[var(--ink)]`}>{grain.t || grain.u}</span>
            <span className="mt-0.5 block truncate text-[10.5px] uppercase tracking-[0.08em] text-[var(--ink2)]">
              {[grain.a, grain.s, grain.d].filter(Boolean).join(" · ")}
            </span>
          </span>
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
