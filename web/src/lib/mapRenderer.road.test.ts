import { afterEach, describe, expect, it } from "vitest";
import type { MapData, MapPoint } from "../api/map";
import { mountMapRenderer } from "./mapRenderer";
import type { MapRenderer } from "./mapRenderer";

const point = (x: number, y: number, z: number, title: string): MapPoint =>
  ({
    x,
    y,
    z3: [x, y, z],
    t: title,
    c: "youtube",
    u: `u:${title}`,
    g: 0,
    r: 0,
    dom: 0,
  }) as MapPoint;

const data = (): MapData =>
  ({
    v: 2,
    points: [point(0, 0, 0, "A"), point(0.4, 0.2, 0.1, "M"), point(0.8, 0.4, 0.2, "B")],
    all: {
      domains: [{ label: "dom", n: 3, x: 0, y: 0 }],
      groups: [{ label: "sub", n: 3, domain: 0 }],
      params: {},
    },
    content: { groups: [], params: {} },
  }) as unknown as MapData;

const frames = (n = 3) =>
  new Promise<void>((resolve) => {
    const step = (left: number) =>
      left <= 0 ? resolve() : requestAnimationFrame(() => step(left - 1));
    step(n);
  });

let renderer: MapRenderer | undefined;
let canvas: HTMLCanvasElement;
let labels: HTMLDivElement;
let leaders: SVGSVGElement;

const mount = (onFocus?: () => void) => {
  canvas = document.createElement("canvas");
  labels = document.createElement("div");
  leaders = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  document.body.append(canvas, leaders, labels);
  renderer = mountMapRenderer(canvas, data(), undefined, labels, onFocus, leaders);
  return renderer;
};

afterEach(() => {
  renderer?.destroy();
  renderer = undefined;
  canvas.remove();
  labels.remove();
  leaders.remove();
});

const ROUTE = [
  { index: 0, kind: "a" as const, title: "A" },
  { index: 1, kind: "stop" as const, title: "M" },
  { index: 2, kind: "b" as const, title: "B" },
];

describe("road overlay", () => {
  it("draws one path vertex per waypoint and a dot each", async () => {
    const r = mount();
    r.setRoute(ROUTE);
    await frames();
    const path = leaders.querySelector("path");
    expect(path).not.toBeNull();
    const d = path!.getAttribute("d") ?? "";
    expect(d.match(/M/g)).toHaveLength(1);
    expect(d.match(/L/g)).toHaveLength(2);
    expect(leaders.querySelectorAll("circle")).toHaveLength(3);
  });

  it("clears when the route is unset and refuses a degenerate one", async () => {
    const r = mount();
    r.setRoute(ROUTE);
    await frames();
    r.setRoute(undefined);
    await frames();
    expect(leaders.querySelectorAll("circle")).toHaveLength(0);
    expect(leaders.querySelector("path")?.getAttribute("d")).toBe("");
    r.setRoute([ROUTE[0]]);
    await frames();
    expect(leaders.querySelectorAll("circle")).toHaveLength(0);
  });

  it("survives the label rebuild that wipes the leaders svg", async () => {
    const r = mount();
    r.setRoute(ROUTE);
    await frames();
    r.setView("content");
    await frames();
    expect(leaders.querySelector("path")).not.toBeNull();
    expect(leaders.querySelectorAll("circle")).toHaveLength(3);
  });

  it("keeps the loop alive: dashes march and the active stop pulses", async () => {
    const r = mount();
    r.setRoute(ROUTE);
    r.setRouteActive(1);
    await frames(2);
    const path = leaders.querySelector("path")!;
    const offset1 = path.getAttribute("stroke-dashoffset");
    const radii = new Set<string>();
    for (let i = 0; i < 6; i++) {
      await frames(3);
      radii.add(leaders.querySelectorAll("circle")[1]!.getAttribute("r")!);
    }
    expect(path.getAttribute("stroke-dashoffset")).not.toBe(offset1);
    expect(radii.size).toBeGreaterThan(1);
    r.setRouteActive(undefined);
    await frames(2);
    expect(leaders.querySelectorAll("circle")[1]!.getAttribute("r")).toBe("3.5");
  });

  it("routes point clicks to the road pick and suspends drill-down focus", async () => {
    let focused = 0;
    const r = mount(() => {
      focused += 1;
    });
    await frames();
    const picks: MapPoint[] = [];
    r.setRoadPick((p) => picks.push(p));
    const rect = canvas.getBoundingClientRect();
    // Point A sits at world origin: with pan 0 and scale 1 it projects to the
    // exact canvas center regardless of orbit angle.
    const cx = rect.left + canvas.clientWidth / 2;
    const cy = rect.top + canvas.clientHeight / 2;
    dispatchEvent(new MouseEvent("mousemove", { clientX: cx, clientY: cy }));
    await frames();
    canvas.dispatchEvent(new MouseEvent("click", { clientX: cx, clientY: cy }));
    expect(picks.map((p) => p.t)).toEqual(["A"]);
    expect(focused).toBe(0);
    r.setRoadPick(undefined);
    canvas.dispatchEvent(new MouseEvent("click", { clientX: cx, clientY: cy }));
    expect(picks).toHaveLength(1);
    expect(focused).toBe(1);
  });
});
