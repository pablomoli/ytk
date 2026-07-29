import { renderHook, act } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { PROFILE_BATCH_PREF, useBatchCursor } from "./useBatchCursor";

beforeEach(() => localStorage.removeItem(PROFILE_BATCH_PREF));

const mount = (gen: string | undefined, batchCount: number) =>
  renderHook(
    ({ g, n }: { g: string | undefined; n: number }) => useBatchCursor(g, n),
    { initialProps: { g: gen, n: batchCount } },
  );

test("reroll survives a remount for the same ranking snapshot (#138)", () => {
  const first = mount("2026-07-29T10:00:00", 5);
  act(() => first.result.current.advance());
  act(() => first.result.current.advance());
  expect(first.result.current.batch).toBe(2);
  first.unmount();

  const second = mount("2026-07-29T10:00:00", 5);
  expect(second.result.current.batch).toBe(2);
});

test("a new ranking snapshot starts at batch 1", () => {
  const first = mount("2026-07-29T10:00:00", 5);
  act(() => first.result.current.advance());
  first.unmount();

  const second = mount("2026-07-29T11:00:00", 5);
  expect(second.result.current.batch).toBe(0);
});

test("the snapshot id arriving after mount hydrates the saved cursor", () => {
  // the ranking query resolves after first render, as in the real inbox
  const saved = mount("gen-a", 5);
  act(() => saved.result.current.advance());
  saved.unmount();

  const { result, rerender } = mount(undefined, 1);
  expect(result.current.batch).toBe(0);
  rerender({ g: "gen-a", n: 5 });
  expect(result.current.batch).toBe(1);
});

test("a stale cursor clamps when the ranking now has fewer batches", () => {
  const first = mount("gen-a", 5);
  act(() => first.result.current.advance());
  act(() => first.result.current.advance());
  act(() => first.result.current.advance());
  expect(first.result.current.batch).toBe(3);
  first.unmount();

  const second = mount("gen-a", 2);
  expect(second.result.current.batch).toBe(1);
});

test("advance wraps at the end", () => {
  const { result } = mount("gen-a", 2);
  act(() => result.current.advance());
  expect(result.current.batch).toBe(1);
  act(() => result.current.advance());
  expect(result.current.batch).toBe(0);
});

test("reset returns to batch 1 and the reset survives a remount", () => {
  const first = mount("gen-a", 5);
  act(() => first.result.current.advance());
  act(() => first.result.current.advance());
  act(() => first.result.current.reset());
  expect(first.result.current.batch).toBe(0);
  first.unmount();

  const second = mount("gen-a", 5);
  expect(second.result.current.batch).toBe(0);
});

test("garbage in storage falls back to batch 1", () => {
  localStorage.setItem(PROFILE_BATCH_PREF, "not json");
  const { result } = mount("gen-a", 5);
  expect(result.current.batch).toBe(0);
});
