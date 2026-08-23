import { page } from "vitest/browser";
import { afterEach, expect, test, vi } from "vitest";
import type { MapData, MapPoint } from "../api/map";
import { mountMapRenderer, type MapRenderer } from "./mapRenderer";

const point = {
  x: 0,
  y: 0,
  z3: [0, 0, 0],
  t: "Knowledge systems",
  c: "youtube",
  u: "u:knowledge",
  g: 0,
  r: 0,
  dom: 0,
} as MapPoint;

const data = {
  v: 2,
  points: [point],
  all: {
    domains: [{ label: "Knowledge", n: 1, x: 0, y: 0 }],
    groups: [{ label: "Systems", n: 1, domain: 0 }],
    params: {},
  },
  content: { groups: [], params: {} },
} as unknown as MapData;

let renderer: MapRenderer | undefined;
let canvas: HTMLCanvasElement;
let labels: HTMLDivElement;

afterEach(() => {
  renderer?.destroy();
  renderer = undefined;
  canvas.remove();
  labels.remove();
});

test("generated map labels are native keyboard-operable focus buttons", async () => {
  // Labels under the open legend's 290px reserve are hidden; the default
  // 414px test viewport puts the only label there.
  await page.viewport(1280, 800);
  canvas = document.createElement("canvas");
  labels = document.createElement("div");
  document.body.append(canvas, labels);
  const onFocus = vi.fn();
  renderer = mountMapRenderer(canvas, data, undefined, labels, onFocus);
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

  const label = labels.querySelector("button");
  expect(label).not.toBeNull();
  expect(label).toHaveAccessibleName("Focus Knowledge");
  expect(label).toHaveAttribute("aria-pressed", "false");
  label!.focus();
  label!.click();
  expect(onFocus).toHaveBeenCalledWith({ dom: 0 });
});

test("renderer exposes home and center-anchored zoom camera commands", () => {
  canvas = document.createElement("canvas");
  labels = document.createElement("div");
  document.body.append(canvas, labels);
  renderer = mountMapRenderer(canvas, data, undefined, labels);

  expect(() => renderer!.zoomBy(1.25)).not.toThrow();
  expect(() => renderer!.resetCamera()).not.toThrow();
});
