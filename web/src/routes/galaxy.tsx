import { useEffect, useRef, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useGalaxy } from "../api/galaxy";
import type { FreshNote } from "../api/fresh";
import { NoteViewer } from "../components/NoteViewer";
import { ErrorState } from "../components/StateViews";
import type { GalaxyHandle } from "../lib/galaxy/scene";
import { mountGalaxy } from "../lib/galaxy/scene";
import { useChromeVisible } from "../lib/chrome";
import "../styles.css";

export const Route = createFileRoute("/galaxy")({ component: GalaxyPage });

const BTN = "rounded px-2 py-1 bg-white/5 hover:bg-white/10";

// NoteViewer's real key is note.path (useNote/useSimilarNotes); the rest is
// display fallback, same minimal contract as lib/orb/note.ts's
// orbPointToFreshNote but for a moon exemplar, which carries no tags/source.
function moonToFreshNote(moon: { path: string; title: string }): FreshNote {
  const base = moon.path.split("/").pop() ?? moon.path;
  return {
    path: moon.path,
    stem: base.replace(/\.md$/, ""),
    title: moon.title,
    url: null,
    source: "",
    date: null,
    added: "",
    thumbnail: null,
    tags: [],
    has_take: false,
  };
}

function GalaxyPage() {
  const chrome = useChromeVisible();
  const galaxy = useGalaxy();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const handleRef = useRef<GalaxyHandle | null>(null);
  const [visiting, setVisiting] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [openMoon, setOpenMoon] = useState<{ path: string; title: string } | null>(null);
  const data = galaxy.data;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const handle = mountGalaxy(canvas, data, {
      onHover: setHovered,
      onVisit: setVisiting,
      onMoonOpen: setOpenMoon,
    });
    handleRef.current = handle;
    return () => {
      handleRef.current = null;
      handle.dispose();
    };
  }, [data]);

  if (galaxy.isError)
    return <ErrorState error={galaxy.error} onRetry={() => void galaxy.refetch()} />;

  const planetByTheme = new Map(data?.planets.map((p) => [p.theme, p]) ?? []);
  const hoveredPlanet = hovered !== null ? planetByTheme.get(hovered) : undefined;
  const visitedPlanet = visiting !== null ? planetByTheme.get(visiting) : undefined;

  return (
    <div className="relative flex-1 min-h-0 overflow-hidden">
      {!data ? (
        <div className="flex-1 grid place-items-center text-sm opacity-60">
          loading the galaxy
        </div>
      ) : (
        <canvas
          ref={canvasRef}
          className={`h-full w-full ${hovered !== null && !openMoon ? "cursor-pointer" : "cursor-grab active:cursor-grabbing"}`}
        />
      )}
      {data && chrome ? (
        <div className="absolute left-4 top-4 flex flex-col gap-2 text-xs">
          <div className="rounded bg-black/60 px-3 py-1">
            {visitedPlanet
              ? `${visitedPlanet.label} · ${visitedPlanet.cls} · ${visitedPlanet.n} · ${visitedPlanet.activity.toFixed(2)} · ${Math.round(visitedPlanet.land_frac * 100)}% land`
              : "overview"}
          </div>
          {visitedPlanet ? (
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                className={BTN}
                onClick={() => handleRef.current?.overview()}
              >
                overview
              </button>
              {visitedPlanet.rings.partners.map((partner) => (
                <button
                  key={partner.theme}
                  type="button"
                  className={BTN}
                  onClick={() => handleRef.current?.visit(partner.theme)}
                >
                  {planetByTheme.get(partner.theme)?.label ?? String(partner.theme)}
                </button>
              ))}
              <button
                type="button"
                className={BTN}
                onClick={() =>
                  void navigate({ to: "/orb", search: { theme: visitedPlanet.theme } })
                }
              >
                land
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      {data && hoveredPlanet && !openMoon ? (
        <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 rounded bg-black/60 px-3 py-1 text-sm">
          {hoveredPlanet.label}
          <span className="ml-2 opacity-60">
            {hoveredPlanet.cls} · {hoveredPlanet.n}
          </span>
        </div>
      ) : null}
      {openMoon ? (
        <NoteViewer note={moonToFreshNote(openMoon)} onClose={() => setOpenMoon(null)} />
      ) : null}
    </div>
  );
}
