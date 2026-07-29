import { describe, expect, test } from "vite-plus/test";
import { Vector3 } from "three";
import { makeNode } from "./types";
import type { SkelNode } from "./types";
import { applyMurrayGirth, trunkRadius } from "./girth";

const node = (y = 0): SkelNode => makeNode(new Vector3(0, y, 0), new Vector3(0, 1, 0));

// An unbranched run of `count` nodes; returns [head, tail].
const chain = (count: number): [SkelNode, SkelNode] => {
  const head = node(0);
  let tail = head;
  for (let i = 1; i < count; i += 1) {
    const next = node(i);
    tail.children.push(next);
    tail = next;
  }
  return [head, tail];
};

// Balanced binary tree: 2^depth tips, each fork separated by `run` nodes so the
// skeleton exercises single-child runs as well as forks.
const balanced = (depth: number, run = 3): SkelNode => {
  const [head, tail] = chain(run);
  if (depth > 0) {
    tail.children.push(balanced(depth - 1, run), balanced(depth - 1, run));
  }
  return head;
};

// A trunk carrying `tips` twigs off one fork: tip count varies, tipRadius does not.
const brush = (tips: number, trunkRun = 4, twigRun = 3): SkelNode => {
  const [head, tail] = chain(trunkRun);
  for (let i = 0; i < tips; i += 1) tail.children.push(chain(twigRun)[0]);
  return head;
};

const walk = (root: SkelNode): SkelNode[] => {
  const out: SkelNode[] = [];
  const stack = [root];
  while (stack.length > 0) {
    const cur = stack.pop() as SkelNode;
    out.push(cur);
    for (const child of cur.children) stack.push(child);
  }
  return out;
};

const expectRelClose = (a: number, b: number, rel = 1e-9) => {
  expect(Math.abs(a - b)).toBeLessThanOrEqual(rel * Math.max(1, Math.abs(a), Math.abs(b)));
};

describe("applyMurrayGirth", () => {
  test.each([2.0, 2.5])("holds the Murray invariant at every fork (n = %s)", (exponent) => {
    const root = balanced(4);
    applyMurrayGirth(root, 0.02, exponent);
    const nodes = walk(root);
    const internal = nodes.filter((n) => n.children.length > 0);
    expect(internal.length).toBeGreaterThan(0);
    for (const n of internal) {
      const sum = n.children.reduce((acc, c) => acc + Math.pow(c.radius, exponent), 0);
      expectRelClose(Math.pow(n.radius, exponent), sum);
    }
    for (const n of nodes.filter((n) => n.children.length === 0)) expect(n.radius).toBe(0.02);
  });

  test("a bigger tree has a thicker trunk at the same tip radius", () => {
    const tipRadius = 0.02;
    const small = balanced(1);
    const large = balanced(6);
    applyMurrayGirth(small, tipRadius, 2.5);
    applyMurrayGirth(large, tipRadius, 2.5);
    expect(trunkRadius(large)).toBeGreaterThan(trunkRadius(small));
  });

  test("trunk radius rises monotonically with tip count", () => {
    const radii = [1, 2, 4, 8, 16, 32, 64].map((tips) => {
      const root = brush(tips);
      applyMurrayGirth(root, 0.02, 2.5);
      return trunkRadius(root);
    });
    for (let i = 1; i < radii.length; i += 1) {
      expect(radii[i] as number).toBeGreaterThan(radii[i - 1] as number);
    }
  });

  test.each([1.5, 2.0, 2.5, 4.0])("an unbranched chain never thickens (n = %s)", (exponent) => {
    const [root] = chain(64);
    applyMurrayGirth(root, 0.03, exponent);
    for (const n of walk(root)) expect(n.radius).toBe(0.03);
  });

  test("survives a 50000-node chain without overflowing the stack", () => {
    const [root] = chain(50_000);
    applyMurrayGirth(root, 0.02, 2.5);
    expect(trunkRadius(root)).toBeCloseTo(0.02, 12);
  });

  test("is deterministic across repeated application", () => {
    const root = balanced(5);
    applyMurrayGirth(root, 0.02, 2.5);
    const first = walk(root).map((n) => n.radius);
    applyMurrayGirth(root, 0.02, 2.5);
    expect(walk(root).map((n) => n.radius)).toEqual(first);
  });
});
