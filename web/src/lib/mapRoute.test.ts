import { describe, expect, it } from "vitest";
import type { MapPoint } from "../api/map";
import type { PathData } from "../api/path";
import { joinRoute } from "./mapRoute";

const point = (u: string): MapPoint =>
  ({ x: 0, y: 0, z3: [0, 0, 0], t: u, c: "youtube", u, g: 0, r: 0, dom: 0 }) as MapPoint;

const note = (url: string, weight = 0.7) => ({ title: url, url, video_id: url, weight });

const path = (stops: PathData["stops"]): PathData => ({
  a: { title: "A", url: "u:a", video_id: "a" },
  b: { title: "B", url: "u:b", video_id: "b" },
  angle_deg: 60,
  background: 0.259,
  stops,
});

const points = [point("u:a"), point("u:mid"), point("u:b"), point("u:other")];

describe("joinRoute", () => {
  it("orders endpoints around stop waypoints and maps stops back", () => {
    const route = joinRoute(
      path([
        { t: 0, support: 0.9, notes: [note("u:other")] },
        { t: 0.5, support: 0.8, notes: [note("u:mid")] },
      ]),
      points,
    );
    expect(route.waypoints.map((w) => w.kind)).toEqual(["a", "stop", "stop", "b"]);
    expect(route.waypoints.map((w) => w.pointIndex)).toEqual([0, 3, 1, 2]);
    expect(route.stopWaypoint).toEqual([1, 2]);
  });

  it("skips waypoints missing from the map, never invents them", () => {
    const route = joinRoute(
      path([
        { t: 0.5, support: 0.8, notes: [note("u:absent")] },
        { t: 0.75, support: 0.7, notes: [] },
      ]),
      points,
    );
    expect(route.waypoints.map((w) => w.kind)).toEqual(["a", "b"]);
    expect(route.stopWaypoint).toEqual([null, null]);
  });

  it("collapses consecutive stops on the same point, keeping best support", () => {
    const route = joinRoute(
      path([
        { t: 0.25, support: 0.6, notes: [note("u:mid")] },
        { t: 0.5, support: 0.8, notes: [note("u:mid")] },
        { t: 0.75, support: 0.7, notes: [note("u:other")] },
      ]),
      points,
    );
    const kinds = route.waypoints.map((w) => w.kind);
    expect(kinds).toEqual(["a", "stop", "stop", "b"]);
    expect(route.waypoints[1].ts).toEqual([0.25, 0.5]);
    expect(route.waypoints[1].support).toBe(0.8);
    expect(route.stopWaypoint).toEqual([1, 1, 2]);
  });

  it("drops an endpoint whose url is not on the map", () => {
    const route = joinRoute(path([]), [point("u:b")]);
    expect(route.waypoints.map((w) => w.kind)).toEqual(["b"]);
  });
});
