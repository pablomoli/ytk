import { Vector3 } from "three";
import { describe, expect, test } from "vite-plus/test";
import { rng } from "./tree";
import { colonize } from "./twigs";
import { makeNode, type SkelNode } from "./types";

const tipAt = (x = 0, y = 0, z = 0): SkelNode =>
  makeNode(new Vector3(x, y, z), new Vector3(0, 1, 0));

const descendants = (root: SkelNode): SkelNode[] => {
  const out: SkelNode[] = [];
  const stack = [...root.children];
  while (stack.length > 0) {
    const node = stack.pop() as SkelNode;
    out.push(node);
    stack.push(...node.children);
  }
  return out;
};

const cloud = (rand: () => number, count: number, center: Vector3, size: number): Vector3[] =>
  Array.from(
    { length: count },
    () =>
      new Vector3(
        center.x + (rand() - 0.5) * size,
        center.y + (rand() - 0.5) * size,
        center.z + (rand() - 0.5) * size,
      ),
  );

describe("space colonization", () => {
  test("grows into a reachable cloud and reports the nodes it added", () => {
    const tip = tipAt();
    const rand = rng(7);
    const added = colonize([tip], {
      attractors: cloud(rand, 400, new Vector3(0, 5, 0), 6),
      step: 0.4,
      killDistance: 0.8,
      attractDistance: 4,
      maxNodes: 2000,
      rand,
    });
    expect(added).toBeGreaterThan(0);
    expect(descendants(tip)).toHaveLength(added);
  });

  test("ignores attractors beyond the attraction distance", () => {
    const tip = tipAt();
    const rand = rng(3);
    const added = colonize([tip], {
      attractors: cloud(rand, 50, new Vector3(0, 100, 0), 2),
      step: 0.4,
      killDistance: 0.8,
      attractDistance: 4,
      maxNodes: 500,
      rand,
    });
    expect(added).toBe(0);
    expect(tip.children).toHaveLength(0);
  });

  test("branches when the cloud is wide and well separated", () => {
    const tip = tipAt();
    const rand = rng(11);
    colonize([tip], {
      attractors: [
        new Vector3(-4, 5, 0),
        new Vector3(4, 5, 0),
        new Vector3(0, 5, 4),
        new Vector3(0, 6, -4),
        new Vector3(-3, 7, 3),
        new Vector3(3, 7, -3),
      ],
      step: 0.5,
      killDistance: 1,
      attractDistance: 12,
      maxNodes: 500,
      rand,
    });
    const forks = [tip, ...descendants(tip)].filter((node) => node.children.length > 1);
    expect(forks.length).toBeGreaterThan(0);
  });

  test("order is preserved along a run and increments on every lateral child", () => {
    const tip = tipAt();
    const rand = rng(7);
    colonize([tip], {
      attractors: cloud(rand, 400, new Vector3(0, 5, 0), 6),
      step: 0.4,
      killDistance: 0.8,
      attractDistance: 4,
      maxNodes: 2000,
      rand,
    });
    const all = [tip, ...descendants(tip)];
    for (const node of all) {
      node.children.forEach((child, index) => {
        expect(child.order).toBe(index === 0 ? node.order : node.order + 1);
      });
    }
    expect(Math.max(...all.map((node) => node.order))).toBeGreaterThan(tip.order);
    expect(all.every((node) => node.radius === 0)).toBe(true);
  });

  test("path length accumulates one step per node", () => {
    const tip = tipAt();
    const rand = rng(7);
    colonize([tip], {
      attractors: cloud(rand, 200, new Vector3(0, 5, 0), 6),
      step: 0.4,
      killDistance: 0.8,
      attractDistance: 4,
      maxNodes: 500,
      rand,
    });
    for (const node of [tip, ...descendants(tip)]) {
      for (const child of node.children) {
        expect(child.pathLength).toBeCloseTo(node.pathLength + 0.4, 9);
        expect(child.position.distanceTo(node.position)).toBeCloseTo(0.4, 9);
      }
    }
  });

  test("every node stays within attractDistance + step of some attractor", () => {
    const tip = tipAt();
    const rand = rng(7);
    const attractors = cloud(rand, 400, new Vector3(0, 5, 0), 6);
    colonize([tip], {
      attractors,
      step: 0.4,
      killDistance: 0.8,
      attractDistance: 4,
      maxNodes: 2000,
      rand,
      jitter: 0.1,
    });
    const bound = 4 + 0.4 + 1e-9;
    const stray = descendants(tip).filter(
      (node) => !attractors.some((a) => a.distanceTo(node.position) <= bound),
    );
    expect(stray).toHaveLength(0);
  });

  test("respects maxNodes exactly", () => {
    const tip = tipAt();
    const rand = rng(5);
    const added = colonize([tip], {
      attractors: cloud(rand, 800, new Vector3(0, 6, 0), 8),
      step: 0.3,
      killDistance: 0.6,
      attractDistance: 5,
      maxNodes: 37,
      rand,
    });
    expect(added).toBe(37);
    expect(descendants(tip)).toHaveLength(37);
  });

  test("is deterministic under identically seeded rngs", () => {
    const run = () => {
      const tip = tipAt();
      const rand = rng(99);
      colonize([tip], {
        attractors: cloud(rng(4), 300, new Vector3(0, 5, 0), 6),
        step: 0.4,
        killDistance: 0.8,
        attractDistance: 4,
        maxNodes: 800,
        rand,
        jitter: 0.15,
      });
      return descendants(tip).map((node) => [
        node.position.x,
        node.position.y,
        node.position.z,
        node.order,
      ]);
    };
    const first = run();
    expect(first.length).toBeGreaterThan(0);
    expect(run()).toEqual(first);
  });

  test("terminates on an empty cloud and on a fully coincident one", () => {
    const empty = tipAt();
    const rand = rng(1);
    expect(
      colonize([empty], {
        attractors: [],
        step: 0.5,
        killDistance: 1,
        attractDistance: 5,
        maxNodes: 100,
        rand,
      }),
    ).toBe(0);
    expect(empty.children).toHaveLength(0);

    const stacked = tipAt();
    const added = colonize([stacked], {
      attractors: Array.from({ length: 500 }, () => new Vector3(0, 3, 0)),
      step: 0.5,
      // zero kill distance is the pathological case: nothing is ever consumed
      // by proximity, so only the iteration cap can stop the loop
      killDistance: 0,
      attractDistance: 5,
      maxNodes: 500,
      rand,
    });
    expect(added).toBeLessThan(500);
    expect(descendants(stacked)).toHaveLength(added);
  });
});
