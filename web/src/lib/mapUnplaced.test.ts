import { describe, expect, it } from "vitest";
import type { MapData, MapDomain, MapGroup } from "../api/map";
import { UNPLACED_LABEL, mapDomainColor, mapSubColor } from "./mapRenderer";

// `unplaced` is not a topic (#106): notes that matched no bucket. It must
// read as absence — grey — and it must not consume a slot on the ramp, or
// unplaced mass growing would silently restyle every real domain.
const domains: MapDomain[] = [
  { label: "epicmap", n: 2062, x: 0, y: 0 },
  { label: UNPLACED_LABEL, n: 662, x: 1, y: 1 },
  { label: "hackathons", n: 620, x: -1, y: -1 },
  { label: "ai-building", n: 429, x: 0.5, y: 0.5 },
];
const groups: MapGroup[] = [
  { label: "County GIS", n: 200, domain: 0, x: 0, y: 0 },
  { label: "loose notes", n: 90, domain: 1, x: 1, y: 1 },
];

const data = (d: MapDomain[] = domains): MapData =>
  ({ v: 2, all: { domains: d, groups } }) as unknown as MapData;

const GREY = "rgb(111, 109, 102)";

describe("unplaced domain colouring", () => {
  it("paints the unplaced domain grey rather than a ramp colour", () => {
    expect(mapDomainColor(data(), 1)).toBe(GREY);
  });

  it("paints real domains with ramp colours, not grey", () => {
    for (const index of [0, 2, 3]) expect(mapDomainColor(data(), index)).not.toBe(GREY);
  });

  it("paints subtopics of the unplaced domain grey too", () => {
    expect(mapSubColor(data(), 1)).toBe(GREY);
    expect(mapSubColor(data(), 0)).not.toBe(GREY);
  });

  it("keeps real domain colours stable when unplaced mass changes", () => {
    // The rank ordering must skip `unplaced`; if it did not, moving it up or
    // down the size order would re-hue every other domain.
    const before = [0, 2, 3].map((i) => mapDomainColor(data(), i));
    const grown = domains.map((d) => (d.label === UNPLACED_LABEL ? { ...d, n: 9999 } : d));
    const after = [0, 2, 3].map((i) => mapDomainColor(data(grown), i));
    expect(after).toEqual(before);
  });

  it("still spans the full ramp when no domain is unplaced", () => {
    const only = domains.filter((d) => d.label !== UNPLACED_LABEL);
    const colors = only.map((_, i) => mapDomainColor(data(only), i));
    expect(new Set(colors).size).toBe(only.length);
  });
});
