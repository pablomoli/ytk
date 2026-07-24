import type { MapDomain, MapGroup, MapPoint } from "../api/map";

// Hierarchy state helpers for the everything view: domains are the controlled
// top level, subtopics the per-domain HDBSCAN children. All pure - the
// renderer consumes the Float32Array targets as uniform arrays.

export type MapFocus = { dom?: number | undefined; sub?: number | undefined };

export const DIM = 0.08;
export const SIBLING = 0.25;

export const ramp = (p: number): number =>
  0.5 - 0.5 * Math.cos(Math.max(0, Math.min(1, p)) * Math.PI);

export const focusLevel = (f: MapFocus): "overview" | "domain" | "sub" =>
  f.dom === undefined ? "overview" : f.sub === undefined ? "domain" : "sub";

export function groupTargets(
  nDom: number,
  groups: MapGroup[],
  focus: MapFocus,
  hover: MapFocus | undefined,
  hiddenDoms: Set<number>,
): { dom: Float32Array; sub: Float32Array } {
  const active = hover?.dom !== undefined ? hover : focus;
  const dom = new Float32Array(nDom);
  for (let d = 0; d < nDom; d++)
    dom[d] = hiddenDoms.has(d) ? 0 : active.dom === undefined || active.dom === d ? 1 : DIM;
  const sub = new Float32Array(groups.length);
  for (let s = 0; s < groups.length; s++) {
    const owner = groups[s].domain ?? -1;
    if (hiddenDoms.has(owner)) {
      sub[s] = 0;
      continue;
    }
    if (active.dom === undefined) {
      sub[s] = 1;
      continue;
    }
    if (owner !== active.dom) {
      sub[s] = DIM;
      continue;
    }
    sub[s] = active.sub === undefined || active.sub === s ? 1 : SIBLING;
  }
  return { dom, sub };
}

export function legendRows(domains: MapDomain[], groups: MapGroup[], focus: MapFocus) {
  return domains
    .map((domain, dom) => ({ dom, label: domain.label, n: domain.n }))
    .filter((row) => row.n > 0)
    .sort((a, b) => b.n - a.n)
    .map((row) => ({
      ...row,
      subs:
        focus.dom === row.dom
          ? groups
              .map((group, sub) => ({ sub, label: group.label, n: group.n, domain: group.domain }))
              .filter((s) => s.domain === row.dom && s.n)
              .sort((a, b) => b.n - a.n)
              .map(({ sub, label, n }) => ({ sub, label, n }))
          : [],
    }));
}

export const slug = (label: string): string =>
  label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

export function focusHash(focus: MapFocus, domains: MapDomain[], groups: MapGroup[]): string {
  if (focus.dom === undefined) return "";
  const dom = slug(domains[focus.dom]?.label ?? "");
  if (!dom) return "";
  if (focus.sub === undefined) return `#d:${dom}`;
  const sub = slug(groups[focus.sub]?.label ?? "");
  return sub ? `#d:${dom}:${sub}` : `#d:${dom}`;
}

export function parseFocusHash(hash: string, domains: MapDomain[], groups: MapGroup[]): MapFocus {
  const m = /^#d:([^:]+)(?::(.+))?$/.exec(hash);
  if (!m) return {};
  const dom = domains.findIndex((d) => slug(d.label) === m[1]);
  if (dom < 0) return {};
  if (!m[2]) return { dom };
  const sub = groups.findIndex((g, i) => g.domain === dom && slug(groups[i].label) === m[2]);
  return sub < 0 ? { dom } : { dom, sub };
}

// The group a point belongs to in a given view: subtopic id (`g`) for the
// "everything" layout, theme id (`th`, content-only) for the "content" layout.
export function pointGroup(point: MapPoint, view: "all" | "content"): number {
  if (view === "content") return point.c3 !== undefined ? (point.th ?? -1) : -1;
  return point.g;
}

// The domain a point belongs to: controlled hierarchy level for the
// everything view, theme for the content view.
export function pointDomain(point: MapPoint, view: "all" | "content"): number {
  if (view === "content") return point.c3 !== undefined ? (point.th ?? -1) : -1;
  return point.dom;
}

export function pointPhases(points: MapPoint[]): Float32Array {
  // Centroids in the all-view 3D layout; group payload centroids are 2D, so
  // accumulate from the points themselves.
  const acc = new Map<string, { x: number; y: number; z: number; n: number }>();
  const key = (p: MapPoint) => (p.g >= 0 ? `s${p.g}` : `d${p.dom}`);
  for (const p of points) {
    const a = acc.get(key(p)) ?? { x: 0, y: 0, z: 0, n: 0 };
    a.x += p.z3[0];
    a.y += p.z3[1];
    a.z += p.z3[2];
    a.n++;
    acc.set(key(p), a);
  }
  const dist = points.map((p) => {
    const a = acc.get(key(p))!;
    return Math.hypot(p.z3[0] - a.x / a.n, p.z3[1] - a.y / a.n, p.z3[2] - a.z / a.n);
  });
  const max = new Map<string, number>();
  points.forEach((p, i) => max.set(key(p), Math.max(max.get(key(p)) ?? 0, dist[i])));
  return new Float32Array(
    points.map((p, i) => {
      const m = max.get(key(p))!;
      return m > 0 ? dist[i] / m : 0;
    }),
  );
}
