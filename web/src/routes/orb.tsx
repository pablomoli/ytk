import { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import type { LayoutName } from "../api/orb";
import { useOrb } from "../api/orb";
import { NoteViewer } from "../components/NoteViewer";
import { ErrorState } from "../components/StateViews";
import type { OrbHandle } from "../lib/orb/scene";
import { mountOrb } from "../lib/orb/scene";
import { orbPointToFreshNote } from "../lib/orb/note";
import "../styles.css";

export const Route = createFileRoute("/orb")({ component: OrbPage });

const LAYOUTS: LayoutName[] = ["radial", "haversine", "lattice"];

function OrbPage() {
  const orb = useOrb();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handleRef = useRef<OrbHandle | null>(null);
  const [layout, setLayout] = useState<LayoutName | null>(null);
  const [theme, setTheme] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [open, setOpen] = useState<{ i: number; rect: DOMRect } | null>(null);
  const data = orb.data;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const handle = mountOrb(canvas, data, {
      onHover: setHovered,
      onOpen: (i, rect) => setOpen({ i, rect }),
    });
    handleRef.current = handle;
    setLayout(data.sphere.chosen);
    return () => {
      handleRef.current = null;
      handle.dispose();
    };
  }, [data]);

  if (orb.isError) return <ErrorState error={orb.error} onRetry={() => void orb.refetch()} />;

  const scores = data?.sphere.scores;
  return (
    <div className="relative flex-1 min-h-0 overflow-hidden">
      <canvas ref={canvasRef} className="h-full w-full cursor-grab active:cursor-grabbing" />
      {data ? (
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
                  title={s ? `trust ${s.trustworthiness.toFixed(3)} overlap ${(100 * s.overlap_frac).toFixed(1)}%` : "unavailable"}
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
              <option key={label} value={i}>{label}</option>
            ))}
          </select>
        </div>
      ) : null}
      {data && hovered !== null && !open ? (
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded bg-black/60 px-3 py-1 text-sm">
          {data.points[hovered].t}
          {data.points[hovered].d ? <span className="ml-2 opacity-60">{data.points[hovered].d}</span> : null}
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
