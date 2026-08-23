import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowsOutIcon,
  CheckIcon,
  CaretLeftIcon,
  CaretRightIcon,
  FunnelIcon,
  GlobeHemisphereWestIcon,
  HouseIcon,
  InfoIcon,
  MinusIcon,
  PathIcon,
  PlusIcon,
  ArticleIcon,
  SlidersHorizontalIcon,
  XIcon,
} from "@phosphor-icons/react";
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
import { Button } from "../components/ui/button";
import { IconButton } from "../components/ui/icon-button";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { SegmentedControl, SegmentedControlItem } from "../components/ui/segmented-control";
import { Toolbar, ToolbarButton } from "../components/ui/toolbar";
import { Tooltip, TooltipContent, TooltipTrigger } from "../components/ui/tooltip";
import {
  initialMapControls,
  mapControlsReducer,
  visibleMapLayers,
  type MapFilter,
  type MapLayer,
} from "../lib/mapControls";
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

function MapToolbarButton({
  label,
  children,
  onClick,
}: {
  label: string;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <ToolbarButton size="icon" aria-label={label} onClick={onClick}>
          <span aria-hidden="true" className="inline-flex [&>svg]:size-5">
            {children}
          </span>
        </ToolbarButton>
      </TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

function RoadPanel({
  ends,
  loading,
  error,
  angle,
  background,
  route,
  activeStop,
  driving,
  candidates,
  onDrive,
  onFly,
  onSetEnd,
  onClose,
}: {
  ends: { a?: MapPoint; b?: MapPoint };
  loading: boolean;
  error: unknown;
  angle?: number | undefined;
  background?: number | undefined;
  route?: MapRoute | undefined;
  activeStop?: number | undefined;
  driving: boolean;
  candidates: MapPoint[];
  onDrive: () => void;
  onFly: (pointIndex: number, waypointIndex: number) => void;
  onSetEnd: (side: "a" | "b", point?: MapPoint) => void;
  onClose: () => void;
}) {
  return (
    <aside className="absolute left-[4rem] top-2 z-10 max-h-[70vh] w-80 overflow-y-auto rounded-card border border-line bg-bg1/90 p-3 font-data text-sm text-ink backdrop-blur">
      <header className="mb-2 flex items-center justify-between">
        <span className="text-xs uppercase tracking-widest text-mute">road</span>
        <span>
          {route ? (
            <button
              className="cursor-pointer appearance-none border-0 bg-transparent px-1 font-data text-xs uppercase tracking-widest text-accent hover:text-ink"
              onClick={onDrive}
            >
              {driving ? "stop" : "drive"}
            </button>
          ) : null}
          <button
            className="inline-flex size-11 cursor-pointer appearance-none items-center justify-center rounded-md border-0 bg-transparent text-mute hover:bg-bg2 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
            onClick={onClose}
            aria-label="Close road mode"
          >
            <XIcon aria-hidden="true" className="size-5" />
          </button>
        </span>
      </header>
      <div className="mb-3 grid gap-2">
        <label className="grid gap-1 text-xs text-mute">
          Road start
          <select
            className="min-h-11 min-w-0 rounded-md border border-line bg-bg2 px-2 text-sm text-ink"
            value={ends.a?.u ?? ""}
            onChange={(event) =>
              onSetEnd("a", candidates.find((point) => point.u === event.target.value))
            }
          >
            <option value="">Choose a note</option>
            {candidates.map((point) => (
              <option key={`a-${point.u}`} value={point.u}>
                {point.t}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs text-mute">
          Road destination
          <select
            className="min-h-11 min-w-0 rounded-md border border-line bg-bg2 px-2 text-sm text-ink"
            value={ends.b?.u ?? ""}
            onChange={(event) =>
              onSetEnd("b", candidates.find((point) => point.u === event.target.value))
            }
          >
            <option value="">Choose a note</option>
            {candidates.map((point) => (
              <option key={`b-${point.u}`} value={point.u}>
                {point.t}
              </option>
            ))}
          </select>
        </label>
      </div>
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
                  className={`grid w-full cursor-pointer appearance-none grid-cols-[2.6rem_1fr] gap-2 rounded border-0 px-1 py-1 text-left font-data text-sm hover:bg-bg2 ${
                    index === activeStop ? "bg-bg2 text-accent" : "bg-transparent text-ink"
                  }`}
                  onClick={() => onFly(waypoint.pointIndex, index)}
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
  const [controls, dispatch] = useReducer(mapControlsReducer, location.hash, initialMapControls);
  const { view, projection, filters, layers, road: roadMode } = controls;
  const flat = projection === "2d";
  const { signal, recent, media, time: timeOn } = filters;
  const { terrain, web, fog, shell: fogShell } = layers;
  const [fogLevel, setFogLevel] = useState(0);
  const [clock, setClock] = useState(1);
  const [pointHover, setPointHover] = useState<MapHover>();
  const [focus, setFocusState] = useState<MapFocus>({});
  const [hover, setHover] = useState<MapFocus>();
  const [hiddenDoms, setHiddenDoms] = useState<Set<number>>(new Set());
  const [legendOpen, setLegendOpen] = useState(true);
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
  // Drive the road: the camera visits each waypoint in order, the itinerary
  // row and the map dot track the current stop, and any manual action stops
  // the tour.
  const [activeStop, setActiveStop] = useState<number | undefined>(undefined);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [driving, setDriving] = useState(false);
  useEffect(() => {
    renderer.current?.setRoute(
      route?.waypoints.map((waypoint) => ({
        index: waypoint.pointIndex,
        kind: waypoint.kind,
        title: waypoint.title,
      })),
    );
    setActiveStop(undefined);
    setDriving(false);
  }, [route]);
  useEffect(() => {
    renderer.current?.setRouteActive(activeStop);
  }, [activeStop]);
  useEffect(() => {
    if (!driving || !route || !map.data) return;
    const stop = activeStop ?? 0;
    if (stop >= route.waypoints.length) {
      setDriving(false);
      setActiveStop(undefined);
      return;
    }
    setActiveStop(stop);
    const point = map.data.points[route.waypoints[stop].pointIndex];
    if (point) renderer.current?.flyTo(point);
    const id = setTimeout(() => setActiveStop(stop + 1), 2200);
    return () => clearTimeout(id);
  }, [driving, activeStop, route, map.data]);
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
    dispatch({ type: "set-view", view: next });
    setFocus({}, next);
    setHiddenDoms(new Set());
    setHover(undefined);
    // Non-content waypoints have no honest position in the content view, so
    // the road does not survive a view switch.
    setRoadEnds({});
  };
  const closeRoad = () => {
    if (roadMode) dispatch({ type: "toggle-road" });
    setRoadEnds({});
  };
  const resetMap = () => {
    dispatch({ type: "reset" });
    setClock(1);
    setFogLevel(0);
    setRoadEnds({});
    setHiddenDoms(new Set());
    setHover(undefined);
    setFocus({}, "all");
    renderer.current?.resetCamera();
  };
  const roadCandidates = map.data!.points
    .filter((point): point is MapPoint & { u: string } => Boolean(point.u))
    .sort((a, b) => a.t.localeCompare(b.t))
    .slice(0, 100);
  const toggleHidden = (dom: number) =>
    setHiddenDoms((current) => {
      const next = new Set(current);
      if (next.has(dom)) next.delete(dom);
      else next.add(dom);
      return next;
    });
  return (
    <div className="map-page">
      <div className="map-stage" aria-label="Knowledge map renderer">
        <canvas ref={canvas} />
        <svg ref={leaders} className="map-leaders" />
        <div ref={labels} className="map-labels" />
        <section
          aria-label="Map controls"
          className="absolute left-2 top-2 z-20 flex max-h-[calc(100%-1rem)] flex-col items-center gap-1 overflow-y-auto text-ink"
        >
          <SegmentedControl
            label="View"
            hideLabel
            orientation="vertical"
            className="gap-1 border-0 bg-transparent p-0"
            value={view}
            onValueChange={(value) => resetView(value as "all" | "content")}
          >
            <Tooltip>
              <SegmentedControlItem value="all" asChild>
                <TooltipTrigger aria-label="Everything">
                  <GlobeHemisphereWestIcon aria-hidden="true" className="size-5" />
                </TooltipTrigger>
              </SegmentedControlItem>
              <TooltipContent side="right">Everything</TooltipContent>
            </Tooltip>
            <Tooltip>
              <SegmentedControlItem value="content" asChild>
                <TooltipTrigger aria-label="Content">
                  <ArticleIcon aria-hidden="true" className="size-5" />
                </TooltipTrigger>
              </SegmentedControlItem>
              <TooltipContent side="right">Content</TooltipContent>
            </Tooltip>
          </SegmentedControl>
          <Popover>
            <PopoverTrigger asChild>
              <IconButton
                label="Filters"
                variant="outline"
                tooltipSide="right"
                aria-pressed={Object.values(filters).some(Boolean)}
              >
                <FunnelIcon />
              </IconButton>
            </PopoverTrigger>
            <PopoverContent side="right" align="start" className="w-72">
              <h2 className="m-0 px-2 py-1 font-data text-xs tracking-[0.08em] text-mute uppercase">
                Filters
              </h2>
              <div className="grid gap-1" role="group" aria-label="Map filters">
                {(["signal", "recent", ...(view === "all" ? ["media" as const] : []), "time"] as MapFilter[]).map(
                  (filter) => (
                    <Button
                      key={filter}
                      variant="ghost"
                      aria-pressed={filters[filter]}
                      className="w-full justify-between aria-pressed:bg-bg3 aria-pressed:font-semibold aria-pressed:text-accent"
                      onClick={() => dispatch({ type: "toggle-filter", filter })}
                    >
                      {filter[0].toUpperCase() + filter.slice(1)}
                      {filters[filter] ? <CheckIcon aria-hidden="true" className="size-4" /> : null}
                    </Button>
                  ),
                )}
              </div>
              {timeOn ? (
                <label className="mt-2 grid gap-1 px-2 font-data text-xs text-mute">
                  Reveal notes through {scrubDate || "latest date"}
                  <input
                    className="min-h-11 w-full accent-accent"
                    type="range"
                    min={0}
                    max={1}
                    step={0.002}
                    value={clock}
                    aria-valuetext={`${shown} of ${dates.length} dated notes through ${scrubDate}`}
                    onChange={(event) => setClock(Number(event.target.value))}
                  />
                </label>
              ) : null}
            </PopoverContent>
          </Popover>
          <SegmentedControl
            label="Projection"
            hideLabel
            orientation="vertical"
            className="gap-1 border-0 bg-transparent p-0"
            value={projection}
            onValueChange={(value) =>
              dispatch({ type: "set-projection", projection: value as "2d" | "3d" })
            }
          >
            <SegmentedControlItem value="2d">2D</SegmentedControlItem>
            <SegmentedControlItem value="3d">3D</SegmentedControlItem>
          </SegmentedControl>
          <Popover>
            <PopoverTrigger asChild>
              <IconButton
                label="Layers"
                variant="outline"
                tooltipSide="right"
                aria-pressed={Object.values(layers).some(Boolean)}
              >
                <SlidersHorizontalIcon />
              </IconButton>
            </PopoverTrigger>
            <PopoverContent side="right" align="start" className="w-64">
              <h2 className="m-0 px-2 py-1 font-data text-xs tracking-[0.08em] text-mute uppercase">
                Layers
              </h2>
              <div className="grid gap-1" role="group" aria-label="Map layers">
                {(Object.keys(visibleMapLayers(layout)) as MapLayer[])
                  .filter((layer) => visibleMapLayers(layout)[layer])
                  .map((layer) => (
                    <Button
                      key={layer}
                      variant="ghost"
                      aria-pressed={layers[layer]}
                      className="w-full justify-between aria-pressed:bg-bg3 aria-pressed:font-semibold aria-pressed:text-accent"
                      onClick={() => dispatch({ type: "toggle-layer", layer })}
                    >
                      {layer[0].toUpperCase() + layer.slice(1)}
                      {layers[layer] ? <CheckIcon aria-hidden="true" className="size-4" /> : null}
                    </Button>
                  ))}
              </div>
              {fog ? (
                <label className="mt-2 grid gap-1 px-2 font-data text-xs text-mute">
                  {fogShell ? "Shell level" : "Fog density"}
                  <input
                    className="min-h-11 w-full accent-accent"
                    type="range"
                    min={0}
                    max={0.9}
                    step={0.01}
                    value={fogLevel}
                    onChange={(event) => setFogLevel(Number(event.target.value))}
                  />
                </label>
              ) : null}
            </PopoverContent>
          </Popover>
          <IconButton
            label="Road"
            variant={roadMode ? "default" : "outline"}
            tooltipSide="right"
            aria-pressed={roadMode}
            onClick={() => (roadMode ? closeRoad() : dispatch({ type: "toggle-road" }))}
          >
            <PathIcon />
          </IconButton>
          <Toolbar label="Map camera" orientation="vertical" className="flex-col gap-1 border-0 bg-transparent p-0">
            <MapToolbarButton label="Home camera" onClick={() => renderer.current?.resetCamera()}>
              <HouseIcon />
            </MapToolbarButton>
            <MapToolbarButton label="Zoom out" onClick={() => renderer.current?.zoomBy(0.8)}>
              <MinusIcon />
            </MapToolbarButton>
            <MapToolbarButton label="Zoom in" onClick={() => renderer.current?.zoomBy(1.25)}>
              <PlusIcon />
            </MapToolbarButton>
            <MapToolbarButton label="Reset map" onClick={resetMap}>
              <ArrowsOutIcon />
            </MapToolbarButton>
            <Popover>
              <Tooltip>
                <TooltipTrigger asChild>
                  <PopoverTrigger asChild>
                    <ToolbarButton size="icon" aria-label="Map help">
                      <InfoIcon aria-hidden="true" className="size-5" />
                    </ToolbarButton>
                  </PopoverTrigger>
                </TooltipTrigger>
                <TooltipContent>Map help</TooltipContent>
              </Tooltip>
              <PopoverContent side="right" align="start" className="w-72 text-sm leading-6 text-ink2">
                <h2 className="m-0 font-data text-xs tracking-[0.08em] text-mute uppercase">
                  Map help
                </h2>
                <p className="mt-2">Drag to orbit in 3D. Right-drag to pan. Scroll or use the camera buttons to zoom.</p>
                <p className="mt-2">Use the Road tool to choose two notes by pointer or with the endpoint selectors.</p>
              </PopoverContent>
            </Popover>
          </Toolbar>
        </section>
        <aside className={`map-legend${legendOpen ? "" : " collapsed"}`}>
          <button
            className="map-legend-toggle"
            onClick={() => setLegendOpen((open) => !open)}
            aria-label={legendOpen ? "Collapse cluster legend" : "Expand cluster legend"}
          >
            {legendOpen ? (
              <CaretRightIcon aria-hidden="true" />
            ) : (
              <CaretLeftIcon aria-hidden="true" />
            )}
          </button>
          {legendOpen ? (
            <>
              {rows.map((row) => (
                <div key={row.dom}>
                  <div className="flex items-center gap-1">
                    <button
                    className={
                      hiddenDoms.has(row.dom) ||
                      (focus.dom !== undefined && focus.dom !== row.dom && hover?.dom !== row.dom)
                        ? "off"
                        : ""
                    }
                    onMouseEnter={() => setHover({ dom: row.dom })}
                    onMouseLeave={() => setHover(undefined)}
                    onFocus={() => setHover({ dom: row.dom })}
                    onBlur={() => setHover(undefined)}
                    aria-pressed={focus.dom === row.dom && focus.sub === undefined}
                    onClick={() =>
                      setFocus(
                        focus.dom === row.dom && focus.sub === undefined ? {} : { dom: row.dom },
                      )
                    }
                  >
                    <i style={{ background: domColor(row.dom) }} />
                    {row.label}
                    <span>{row.n}</span>
                    </button>
                    <label className="inline-flex size-11 shrink-0 cursor-pointer items-center justify-center" title={`Show ${row.label}`}>
                      <input
                        type="checkbox"
                        checked={!hiddenDoms.has(row.dom)}
                        aria-label={`Show ${row.label}`}
                        onChange={() => toggleHidden(row.dom)}
                      />
                    </label>
                  </div>
                  {row.subs.map((s) => (
                    <button
                      key={s.sub}
                      className={`sub${hiddenDoms.has(row.dom) || (focus.sub !== undefined && focus.sub !== s.sub && hover?.sub !== s.sub) ? " off" : ""}`}
                      onMouseEnter={() => setHover({ dom: row.dom, sub: s.sub })}
                      onMouseLeave={() => setHover(undefined)}
                      onFocus={() => setHover({ dom: row.dom, sub: s.sub })}
                      onBlur={() => setHover(undefined)}
                      aria-pressed={focus.sub === s.sub}
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
                <strong>{visibleNotes} notes</strong>
                <details className="mt-2" open={diagnosticsOpen}>
                  <summary
                    className="min-h-11 cursor-pointer py-3"
                    onClick={(event) => {
                      event.preventDefault();
                      setDiagnosticsOpen((open) => !open);
                    }}
                  >
                    Diagnostics
                  </summary>
                  {diagnosticsOpen ? (
                    <p>
                      trust {trust?.toFixed(2) ?? "n/a"} · silhouette{" "}
                      {layout.params.silhouette?.toFixed(2) ?? "n/a"}
                    </p>
                  ) : null}
                </details>
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
            activeStop={activeStop}
            driving={driving}
            candidates={roadCandidates}
            onDrive={() => {
              setActiveStop(undefined);
              setDriving((current) => !current);
            }}
            onFly={(pointIndex, waypointIndex) => {
              setDriving(false);
              setActiveStop(waypointIndex);
              const point = map.data?.points[pointIndex];
              if (point) renderer.current?.flyTo(point);
            }}
            onSetEnd={(side, point) =>
              setRoadEnds((current) => {
                const other = side === "a" ? current.b : current.a;
                const keep = other ? (side === "a" ? { b: other } : { a: other }) : {};
                if (!point || point.u === other?.u) return keep;
                return side === "a" ? { ...keep, a: point } : { ...keep, b: point };
              })
            }
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
