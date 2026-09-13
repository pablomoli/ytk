import { expect, test } from "vitest";
import { ago, byStation, heldFor, inkWeight, logp, scaleT, walkOrder } from "./packetModel";
import type { TrackPacket } from "../api/packet";

const pk = (id: number, name: string, since: string, tokens = 0): TrackPacket => ({
  id,
  title: `p${id}`,
  source: "youtube",
  station: { name, since, note: "", model: false },
  rounds: 0,
  calls: 0,
  tokens,
});

test("a minute to ten days fills the ring", () => {
  expect(logp(0)).toBe(0);
  expect(logp(10 * 86400)).toBeCloseTo(1, 2);
  expect(scaleT(3600)).toBeGreaterThan(scaleT(60));
  expect(scaleT(10 * 86400)).toBeCloseTo(1, 1);
});

test("held time comes from the station's since", () => {
  const now = Date.parse("2026-09-06T22:20:00Z");
  expect(
    heldFor({ name: "owner", since: "2026-09-06T22:12:00Z", note: "", model: false }, now),
  ).toBe(480);
  expect(ago(480)).toBe("8 m 00 s");
  expect(ago(90000)).toBe("1 d 01 h");
});

test("walk order is station by station, longest held first", () => {
  const now = Date.parse("2026-09-06T22:20:00Z");
  const packets = [
    pk(1, "owner", "2026-09-06T22:19:00Z"),
    pk(2, "runner", "2026-09-06T22:18:00Z"),
    pk(3, "owner", "2026-09-06T22:10:00Z"),
    pk(4, "student", "2026-09-06T22:19:30Z"),
  ];
  expect(walkOrder(packets, now)).toEqual([2, 4, 3, 1]);
  expect(byStation(packets, now)[6]!.map((p) => p.id)).toEqual([3, 1]);
});

test("ink weight is clamped to a quarter and three times the mean", () => {
  expect(inkWeight(0, 1000)).toBe(0.25);
  expect(inkWeight(9000, 1000)).toBe(3);
  expect(inkWeight(500, 1000)).toBe(0.5);
});
