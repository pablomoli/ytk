import type { MapPoint } from "../api/map";
import type { PathData } from "../api/path";

// Joins a /api/path itinerary to map points. The join key is the note url:
// both sides read the same `url` metadata from the videos collection
// (build_map.py emits it as `u`), so equality is exact for every video note.
// Waypoints missing from the map are skipped, never invented. Positions are
// deliberately absent — the map morphs between views, so the overlay resolves
// screen positions per frame from pointIndex, exactly like labels do.
export type RouteWaypoint = {
  pointIndex: number;
  kind: "a" | "stop" | "b";
  ts: number[];
  title: string;
  url: string | null;
  support: number | null;
};

export type MapRoute = {
  waypoints: RouteWaypoint[];
  // stops[i] -> index into waypoints, null when the stop has no note on the map
  stopWaypoint: Array<number | null>;
};

export function joinRoute(path: PathData, points: MapPoint[]): MapRoute {
  const byUrl = new Map<string, number>();
  points.forEach((point, index) => {
    if (point.u && !byUrl.has(point.u)) byUrl.set(point.u, index);
  });

  const waypoints: RouteWaypoint[] = [];
  const stopWaypoint: Array<number | null> = [];

  const push = (waypoint: RouteWaypoint): number | null => {
    const last = waypoints[waypoints.length - 1];
    if (last && last.pointIndex === waypoint.pointIndex && last.kind === waypoint.kind) {
      last.ts.push(...waypoint.ts);
      if (waypoint.support !== null)
        last.support = last.support === null ? waypoint.support : Math.max(last.support, waypoint.support);
      return waypoints.length - 1;
    }
    waypoints.push(waypoint);
    return waypoints.length - 1;
  };

  const endpoint = (which: "a" | "b") => {
    const note = path[which];
    const index = note.url ? byUrl.get(note.url) : undefined;
    if (index === undefined) return;
    push({ pointIndex: index, kind: which, ts: [], title: note.title, url: note.url, support: null });
  };

  endpoint("a");
  for (const stop of path.stops) {
    const top = stop.notes[0];
    const index = top?.url ? byUrl.get(top.url) : undefined;
    if (index === undefined) {
      stopWaypoint.push(null);
      continue;
    }
    stopWaypoint.push(
      push({
        pointIndex: index,
        kind: "stop",
        ts: [stop.t],
        title: top.title,
        url: top.url,
        support: stop.support,
      }),
    );
  }
  endpoint("b");

  return { waypoints, stopWaypoint };
}
