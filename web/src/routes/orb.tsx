import { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import type { LayoutName } from "../api/orb";
import { useOrb } from "../api/orb";
import { apiGet, queryClient } from "../api/client";
import type { SimilarItem } from "../api/fresh";
import { NoteViewer } from "../components/NoteViewer";
import { ErrorState } from "../components/StateViews";
import type { OrbHandle, OrbViewMode } from "../lib/orb/scene";
import { mountOrb } from "../lib/orb/scene";
import { orbPointToFreshNote } from "../lib/orb/note";
import { useChromeVisible } from "../lib/chrome";
import { validateOrbSearch } from "./orbSearch";
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

const LAYOUTS: LayoutName[] = ["radial", "haversine", "lattice"];

// build_map sometimes emits raw Obsidian embed syntax in titles; strip for display only
const captionTitle = (t: string) =>
  t.replace(/!\[\[([^\]]+)\]\]/g, "$1").trim();

function OrbPage() {
  const chrome = useChromeVisible();
  const orb = useOrb();
  const searchTheme = Route.useSearch().theme;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handleRef = useRef<OrbHandle | null>(null);
  const [layout, setLayout] = useState<LayoutName | null>(null);
  const [viewMode, setViewMode] = useState<OrbViewMode>("inside");
  const [theme, setTheme] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [open, setOpen] = useState<{ i: number; rect: DOMRect } | null>(null);
  const data = orb.data;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const handle = mountOrb(canvas, data, {
      onHover: (i) => {
        setHovered(i);
        if (i !== null) prefetchNote(data.points[i].p);
      },
      onOpen: (i, rect) => setOpen({ i, rect }),
    });
    handleRef.current = handle;
    setLayout(data.sphere.chosen);
    setViewMode("inside"); // matches the freshly mounted handle's initial mode
    // ?theme= deep-link from /galaxy's "land" button: apply to the freshly
    // mounted handle, not just state, so a fresh navigation lands filtered
    if (searchTheme !== undefined) {
      setTheme(searchTheme);
      handle.setThemeFilter(searchTheme);
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
  return (
    <div className="relative flex-1 min-h-0 overflow-hidden">
      {!data ? (
        <div className="flex-1 grid place-items-center text-sm opacity-60">
          loading the sphere
        </div>
      ) : (
        <canvas
          ref={canvasRef}
          className={`h-full w-full ${hovered !== null && !open ? "cursor-pointer" : "cursor-grab active:cursor-grabbing"}`}
        />
      )}
      {data && chrome ? (
        <div className="absolute left-4 top-4 flex flex-col gap-2 text-xs">
          <div className="flex gap-1">
            {LAYOUTS.map((name) => {
              const missing = name === "haversine" && !data.sphere.haversine;
              const s = scores?.[name];
              return (
                <button
                  key={name}
                  type="button"
                  disabled={missing}
                  title={
                    s
                      ? `trust ${s.trustworthiness.toFixed(3)} overlap ${(100 * s.overlap_frac).toFixed(1)}%`
                      : "unavailable"
                  }
                  className={`rounded px-2 py-1 ${layout === name ? "bg-white/20" : "bg-white/5 hover:bg-white/10"} disabled:opacity-30`}
                  onClick={() => {
                    setLayout(name);
                    handleRef.current?.setLayout(name);
                  }}
                >
                  {name}
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
          </div>
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
      {data && hovered !== null && !open ? (
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded bg-black/60 px-3 py-1 text-sm">
          {captionTitle(data.points[hovered].t)}
          {data.points[hovered].d ? (
            <span className="ml-2 opacity-60">{data.points[hovered].d}</span>
          ) : null}
        </div>
      ) : null}
      {data && open ? (
        <NoteViewer
          note={orbPointToFreshNote(data.points[open.i])}
          originRect={open.rect}
          onClose={() => {
            setOpen(null);
            handleRef.current?.blur();
          }}
        />
      ) : null}
    </div>
  );
}
