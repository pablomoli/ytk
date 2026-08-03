import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMap, isMapV2 } from "../api/map";
import type { MapData, MapDomain, MapPoint } from "../api/map";
import { usePath } from "../api/path";
import { ApiError } from "../api/client";
import { joinRoute } from "../lib/mapRoute";
import type { MapRoute } from "../lib/mapRoute";
import { ErrorState } from "../components/StateViews";
import { mapDomainColor, mapGroupColor, mapSubColor, mountMapRenderer } from "../lib/mapRenderer";
import type { MapHover } from "../lib/mapRenderer";
import { focusHash, legendRows, parseFocusHash } from "../lib/mapGroups";
import type { MapFocus } from "../lib/mapGroups";
import { HubControls } from "../components/HubControls";
import "../styles.css";

export const Route = createFileRoute("/map")({ component: MapPage });

// Content view has no domain/subtopic split - its themes stand in as a flat
// domain list so legendRows can drive both views with one code path.
const contentAsDomains = (data: MapData): MapDomain[] =>
  data.content.groups.map((group) => ({
    label: group.label,
    n: group.n,
    x: group.x ?? 0,
    y: group.y ?? 0,
  }));

function hoverLabels(
  data: MapData,
  view: "all" | "content",
  point: MapPoint,
): { domain: string; sub?: string | undefined } {
  if (view === "content") return { domain: data.content.groups[point.th ?? -1]?.label || "dust" };
  return {
    domain: data.all.domains[point.dom]?.label || "dust",
    sub: point.g >= 0 ? data.all.groups[point.g]?.label : undefined,
  };
}

function MapTooltip({
  hover,
  domain,
  sub,
}: {
  hover: MapHover;
  domain: string;
  sub?: string | undefined;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: hover.x + 14, top: hover.y + 14 });
  useLayoutEffect(() => {
    const height = ref.current?.offsetHeight ?? 0;
    setPosition({
      left: Math.min(hover.x + 14, innerWidth - 320),
      top: Math.min(hover.y + 14, innerHeight - height - 16),
    });
  }, [hover]);
  const signal = ["", "saved", "thought", "directive"][hover.point.r] || "";
  return (
    <div ref={ref} className="map-tip" style={position}>
      {hover.point.img && hover.point.u ? (
        <img src={`/api/cover?u=${encodeURIComponent(hover.point.u)}`} alt="" />
      ) : null}
      <div>{hover.point.t}</div>
      <small>
        {hover.point.c} · {domain}
        {sub ? ` · ${sub}` : ""}
        {signal ? ` · ${signal}` : ""}
        {hover.point.d ? ` · ${hover.point.d}` : ""}
      </small>
    </div>
  );
}

const pathErrorDetail = (error: unknown): string => {
  if (error instanceof ApiError && typeof error.body === "object" && error.body !== null) {
    const detail = (error.body as Record<string, unknown>).detail;
    if (typeof detail === "string") return detail;
  }
  return error instanceof Error ? error.message : "path request failed";
};

function RoadPanel({
  ends,
  loading,
  error,
  angle,
  background,
  route,
  onFly,
  onClose,
}: {
  ends: { a?: MapPoint; b?: MapPoint };
  loading: boolean;
  error: unknown;
  angle?: number | undefined;
  background?: number | undefined;
  route?: MapRoute | undefined;
  onFly: (pointIndex: number) => void;
  onClose: () => void;
}) {
  return (
    <aside className="absolute left-3 top-14 z-10 max-h-[70vh] w-80 overflow-y-auto rounded-card border border-line bg-bg1/90 p-3 font-data text-sm text-ink backdrop-blur">
      <header className="mb-2 flex items-center justify-between">
        <span className="text-xs uppercase tracking-widest text-mute">road</span>
        <button
          className="cursor-pointer appearance-none border-0 bg-transparent px-1 font-data text-sm text-mute hover:text-ink"
          onClick={onClose}
          aria-label="Close road mode"
        >
          x
        </button>
      </header>
      {!ends.a ? <p className="text-mute">click a note to start the road</p> : null}
      {ends.a && !ends.b ? (
        <p className="text-mute">
          from <span className="text-ink">{ends.a.t}</span> - click the destination
        </p>
      ) : null}
      {loading ? <p className="text-mute">routing...</p> : null}
      {error != null ? (
        <p className="text-live" role="alert">
          {pathErrorDetail(error)}
        </p>
      ) : null}
      {route ? (
        <>
          <p className="mb-2 text-xs text-mute">
            {angle?.toFixed(1)}&deg; apart &middot; background {background?.toFixed(3)}
          </p>
          <ol className="m-0 list-none p-0" aria-label="Road itinerary">
            {route.waypoints.map((waypoint, index) => (
              <li key={index}>
                <button
                  className="grid w-full cursor-pointer appearance-none grid-cols-[2.6rem_1fr] gap-2 rounded border-0 bg-transparent px-1 py-1 text-left font-data text-sm text-ink hover:bg-bg2"
                  onClick={() => onFly(waypoint.pointIndex)}
                >
                  <span className="text-xs leading-5 text-mute">
                    {waypoint.kind === "stop" ? waypoint.ts[0]?.toFixed(2) : waypoint.kind}
                  </span>
                  <span>
                    {waypoint.title}
                    {waypoint.support !== null ? (
                      <span className="ml-1 text-xs text-accent">{waypoint.support.toFixed(3)}</span>
                    ) : null}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </aside>
  );
}

function MapPage() {
  const map = useMap();
  const canvas = useRef<HTMLCanvasElement>(null);
  const labels = useRef<HTMLDivElement>(null);
  const leaders = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<"all" | "content">(
    location.hash === "#content" ? "content" : "all",
  );
  const [flat, setFlat] = useState(location.hash === "#2d");
  const [terrain, setTerrain] = useState(false);
  const [web, setWeb] = useState(false);
  const [fog, setFog] = useState(false);
  const [fogLevel, setFogLevel] = useState(0);
  const [fogShell, setFogShell] = useState(false);
  const [signal, setSignal] = useState(false);
  const [recent, setRecent] = useState(false);
  const [media, setMedia] = useState(false);
  const [timeOn, setTimeOn] = useState(false);
  const [clock, setClock] = useState(1);
  const [pointHover, setPointHover] = useState<MapHover>();
  const [focus, setFocusState] = useState<MapFocus>({});
  const [hover, setHover] = useState<MapFocus>();
  const [hiddenDoms, setHiddenDoms] = useState<Set<number>>(new Set());
  const [legendOpen, setLegendOpen] = useState(true);
  const [roadMode, setRoadMode] = useState(false);
  const [roadEnds, setRoadEnds] = useState<{ a?: MapPoint; b?: MapPoint }>({});
  const renderer = useRef<ReturnType<typeof mountMapRenderer> | undefined>(undefined);
  const flatRef = useRef(flat);
  useEffect(() => {
    flatRef.current = flat;
  }, [flat]);
  // Focus changes rewrite the hash to #d:<domain>[:<sub>]; clearing focus
  // falls back to the dimension flag (#content is a one-shot deep-link read
  // at mount only, never round-tripped through interactive state changes).
  // In content view focus.dom indexes the theme list, not map.data.all.domains,
  // so a #d: hash would name an unrelated domain - the hash stays #content
  // for the whole content-view lifetime, focused or not.
  // forView covers view switches: setView is async, so resetView passes the
  // incoming view instead of letting the closure read the outgoing one.
  const setFocus = (next: MapFocus, forView: "all" | "content" = view) => {
    setFocusState(next);
    if (!map.data) return;
    if (forView === "content") {
      history.replaceState(null, "", location.pathname + "#content");
      return;
    }
    const h = focusHash(next, map.data.all.domains, map.data.all.groups);
    history.replaceState(null, "", h || location.pathname + (flatRef.current ? "#2d" : ""));
  };
  const setFocusRef = useRef(setFocus);
  useEffect(() => {
    setFocusRef.current = setFocus;
  });
  useEffect(() => {
    if (!map.data || !canvas.current) return;
    // A #d: hash only ever encodes an all-view domain (content view keeps
    // #content); view state already agrees with the hash at mount.
    if (view === "all")
      setFocusState(parseFocusHash(location.hash, map.data.all.domains, map.data.all.groups));
    renderer.current = mountMapRenderer(
      canvas.current,
      map.data,
      setPointHover,
      labels.current ?? undefined,
      (next) => setFocusRef.current(next),
      leaders.current ?? undefined,
      { intro: !location.hash.startsWith("#d:") },
    );
    return () => renderer.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map.data]);
  useEffect(() => {
    renderer.current?.setView(view);
  }, [view]);
  useEffect(() => {
    renderer.current?.setDimension(flat);
  }, [flat]);
  useEffect(() => {
    renderer.current?.setTerrain(terrain);
  }, [terrain]);
  useEffect(() => {
    renderer.current?.setWeb(web);
  }, [web]);
  useEffect(() => {
    renderer.current?.setFog(fog);
  }, [fog]);
  useEffect(() => {
    renderer.current?.setFogLevel(fogLevel);
  }, [fogLevel]);
  useEffect(() => {
    renderer.current?.setFogShell(fogShell);
  }, [fogShell]);
  useEffect(() => {
    // The lens only means anything on the everything view — the content view
    // is already nothing but media.
    renderer.current?.setFilters(signal, recent, media && view === "all");
  }, [signal, recent, media, view]);
  useEffect(() => {
    // Off means "show everything", not "show nothing" — the scrubber's own
    // position is remembered so toggling back resumes where it was left.
    renderer.current?.setClock(timeOn ? clock : 1);
  }, [timeOn, clock]);
  useEffect(() => {
    renderer.current?.setFocus(focus);
  }, [focus]);
  useEffect(() => {
    renderer.current?.setHover(hover);
  }, [hover]);
  useEffect(() => {
    renderer.current?.setHiddenDomains(hiddenDoms);
  }, [hiddenDoms]);
  useEffect(() => {
    renderer.current?.setLegendOpen(legendOpen);
  }, [legendOpen]);
  // Two picks fill A then B; a third starts a new road. Points without a url
  // cannot resolve as /api/path endpoints, so they are ignored.
  useEffect(() => {
    renderer.current?.setRoadPick(
      roadMode
        ? (point) => {
            if (!point.u) return;
            setRoadEnds((ends) =>
              !ends.a || ends.b
                ? { a: point }
                : point.u === ends.a.u
                  ? ends
                  : { a: ends.a, b: point },
            );
          }
        : undefined,
    );
  }, [roadMode, map.data]);
  const roadPath = usePath(roadEnds.a?.u ?? undefined, roadEnds.b?.u ?? undefined);
  const route = useMemo(
    () =>
      roadPath.data && map.data ? joinRoute(roadPath.data, map.data.points) : undefined,
    [roadPath.data, map.data],
  );
  useEffect(() => {
    renderer.current?.setRoute(
      route?.waypoints.map((waypoint) => ({
        index: waypoint.pointIndex,
        kind: waypoint.kind,
        title: waypoint.title,
      })),
    );
  }, [route]);
  // Scrubber readout. The slider's position is a quantile, so the date it
  // corresponds to has to be looked up in the sorted dates rather than
  // interpolated between the endpoints — that is the whole point of ranking.
  // Declared above the loading guard: hooks must run on every render path.
  const dates = useMemo(
    () =>
      (map.data?.points ?? [])
        .map((point) => point.d)
        .filter((d): d is string => Boolean(d))
        .sort(),
    [map.data],
  );
  const shown = dates.length ? Math.round(clock * (dates.length - 1)) + 1 : 0;
  const scrubDate = dates.length ? dates[Math.min(shown, dates.length) - 1] : "";
  if (map.isLoading) return <div className="map-state">loading map...</div>;
  if (map.isError)
    return (
      <div className="map-state">
        <ErrorState error={map.error} />
      </div>
    );
  if (map.data && !isMapV2(map.data))
    return (
      <div className="map-state">
        map data predates the domain hierarchy - run `uv run python scripts/build_map.py`
      </div>
    );
  const hoverInfo = pointHover ? hoverLabels(map.data!, view, pointHover.point) : undefined;
  const layout = view === "content" ? map.data!.content : map.data!.all;
  const rows = legendRows(
    view === "content" ? contentAsDomains(map.data!) : map.data!.all.domains,
    view === "content" ? [] : map.data!.all.groups,
    focus,
  );
  const domColor = (index: number) =>
    view === "content"
      ? mapGroupColor(map.data!, "content", index)
      : mapDomainColor(map.data!, index);
  const visibleNotes =
    view === "content"
      ? map.data!.points.filter((point) => point.c3).length
      : map.data!.points.length;
  const trust = layout.params.trustworthiness_3d ?? layout.params.trustworthiness;
  const resetView = (next: "all" | "content") => {
    setView(next);
    setFocus({}, next);
    setHiddenDoms(new Set());
    setHover(undefined);
    // Non-content waypoints have no honest position in the content view, so
    // the road does not survive a view switch.
    setRoadMode(false);
    setRoadEnds({});
  };
  const closeRoad = () => {
    setRoadMode(false);
    setRoadEnds({});
  };
  const toggleHidden = (dom: number) =>
    setHiddenDoms((current) => {
      const next = new Set(current);
      if (next.has(dom)) next.delete(dom);
      else next.add(dom);
      return next;
    });
  return (
    <div className="map-page">
      <HubControls className="absolute top-3 right-4 z-10 p-0">
        <span className="count">{map.data?.points.length ?? 0} notes</span>
      </HubControls>
      <div className="map-controls" aria-label="Map controls">
        <div>
          <button
            className={`fchip${view === "all" ? " on" : ""}`}
            onClick={() => resetView("all")}
          >
            everything
          </button>
          <button
            className={`fchip${view === "content" ? " on" : ""}`}
            onClick={() => resetView("content")}
          >
            content
          </button>
        </div>
        <div>
          <button
            className={`fchip${signal ? " on" : ""}`}
            onClick={() => setSignal((current) => !current)}
          >
            signal
          </button>
          <button
            className={`fchip${recent ? " on" : ""}`}
            onClick={() => setRecent((current) => !current)}
          >
            recent
          </button>
          {view === "all" ? (
            <button
              className={`fchip${media ? " on" : ""}`}
              onClick={() => setMedia((current) => !current)}
              title="Dim session and memory notes so consumed media reads in place"
            >
              media
            </button>
          ) : null}
          <button
            className={`fchip${timeOn ? " on" : ""}`}
            onClick={() => setTimeOn((current) => !current)}
            title="Sweep notes in by the date they were born"
          >
            time
          </button>
          <button className="fchip" onClick={() => setFlat((current) => !current)}>
            {flat ? "3d" : "2d"}
          </button>
          <button
            className={`fchip${roadMode ? " on" : ""}`}
            onClick={() => (roadMode ? closeRoad() : setRoadMode(true))}
            title="Pick two notes and walk the slerp road between them"
          >
            road
          </button>
        </div>
        {timeOn ? (
          <div className="map-scrub">
            <input
              type="range"
              min={0}
              max={1}
              step={0.002}
              value={clock}
              aria-label="Time machine: reveal notes up to this date"
              onChange={(event) => setClock(Number(event.target.value))}
            />
            <span>
              {scrubDate}
              <em>
                {shown} / {dates.length}
              </em>
            </span>
          </div>
        ) : null}
        <div>
          {map.data?.all.terrain || map.data?.content.terrain ? (
            <button
              className={`fchip${terrain ? " on" : ""}`}
              onClick={() => {
                setWeb(false);
                setTerrain((current) => !current);
              }}
            >
              terrain
            </button>
          ) : null}
          {map.data?.all.web || map.data?.content.web ? (
            <button
              className={`fchip${web ? " on" : ""}`}
              onClick={() => {
                if (!web) {
                  setTerrain(false);
                  setFlat(false);
                }
                setWeb((current) => !current);
              }}
            >
              web
            </button>
          ) : null}
          {map.data?.all.fog || map.data?.content.fog ? (
            <button
              className={`fchip${fog ? " on" : ""}`}
              onClick={() => {
                if (!fog) {
                  setTerrain(false);
                  setFlat(false);
                }
                setFog((current) => !current);
              }}
            >
              fog
            </button>
          ) : null}
          {fog ? (
            <button
              className={`fchip${fogShell ? " on" : ""}`}
              onClick={() => setFogShell((current) => !current)}
              title="show only the shell |density - level| < 0.06: a pseudo-isosurface at the slider's level"
            >
              shell
            </button>
          ) : null}
        </div>
        {fog ? (
          <input
            className="fog-level"
            type="range"
            min={0}
            max={0.9}
            step={0.01}
            value={fogLevel}
            onChange={(event) => setFogLevel(Number(event.target.value))}
            title={
              fogShell
                ? "isosurface level: slide to sweep the shell through the density field"
                : "density threshold: slide up to shrink the fog to its cores"
            }
          />
        ) : null}
      </div>
      <div className="map-stage" aria-label="Knowledge map renderer">
        <canvas ref={canvas} />
        <svg ref={leaders} className="map-leaders" />
        <div ref={labels} className="map-labels" />
        <aside className={`map-legend${legendOpen ? "" : " collapsed"}`}>
          <button
            className="map-legend-toggle"
            onClick={() => setLegendOpen((open) => !open)}
            aria-label={legendOpen ? "Collapse cluster legend" : "Expand cluster legend"}
          >
            {legendOpen ? "›" : "‹"}
          </button>
          {legendOpen ? (
            <>
              {rows.map((row) => (
                <div key={row.dom}>
                  <button
                    className={
                      hiddenDoms.has(row.dom) ||
                      (focus.dom !== undefined && focus.dom !== row.dom && hover?.dom !== row.dom)
                        ? "off"
                        : ""
                    }
                    onMouseEnter={() => setHover({ dom: row.dom })}
                    onMouseLeave={() => setHover(undefined)}
                    onClick={(event) => {
                      if (event.altKey) toggleHidden(row.dom);
                      else
                        setFocus(
                          focus.dom === row.dom && focus.sub === undefined ? {} : { dom: row.dom },
                        );
                    }}
                  >
                    <i style={{ background: domColor(row.dom) }} />
                    {row.label}
                    <span>{row.n}</span>
                  </button>
                  {row.subs.map((s) => (
                    <button
                      key={s.sub}
                      className={`sub${hiddenDoms.has(row.dom) || (focus.sub !== undefined && focus.sub !== s.sub && hover?.sub !== s.sub) ? " off" : ""}`}
                      onMouseEnter={() => setHover({ dom: row.dom, sub: s.sub })}
                      onMouseLeave={() => setHover(undefined)}
                      onClick={() =>
                        setFocus(
                          focus.sub === s.sub ? { dom: row.dom } : { dom: row.dom, sub: s.sub },
                        )
                      }
                    >
                      <i style={{ background: mapSubColor(map.data!, s.sub) }} />
                      {s.label}
                      <span>{s.n}</span>
                    </button>
                  ))}
                </div>
              ))}
              <footer>
                {visibleNotes} notes · trust {trust?.toFixed(2) ?? "n/a"} · sil{" "}
                {layout.params.silhouette?.toFixed(2) ?? "n/a"}
                <br />
                drag orbit · right-drag pan · scroll zoom
              </footer>
            </>
          ) : (
            <div className="map-legend-dots">
              {rows.slice(0, 10).map((row) => (
                <i key={row.dom} style={{ background: domColor(row.dom) }} />
              ))}
            </div>
          )}
        </aside>
        {roadMode ? (
          <RoadPanel
            ends={roadEnds}
            loading={roadPath.isLoading}
            error={roadPath.error}
            angle={roadPath.data?.angle_deg}
            background={roadPath.data?.background}
            route={route}
            onFly={(pointIndex) => {
              const point = map.data?.points[pointIndex];
              if (point) renderer.current?.flyTo(point);
            }}
            onClose={closeRoad}
          />
        ) : null}
        {pointHover && hoverInfo ? (
          <MapTooltip hover={pointHover} domain={hoverInfo.domain} sub={hoverInfo.sub} />
        ) : null}
      </div>
    </div>
  );
}
