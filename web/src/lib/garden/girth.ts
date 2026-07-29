// Stage 3: girth. One bottom-up pass over a finished skeleton.
import type { SkelNode } from "./types";

// Murray's law: r^n at a fork equals the sum of the children's r^n. n = 2 is
// cross-section preservation (da Vinci); ~2.5 is the empirical fit for trees.
export function applyMurrayGirth(root: SkelNode, tipRadius: number, exponent: number): void {
  // Explicit traversal, never recursion: runs reach tens of thousands of
  // single-child nodes and the call stack would overflow.
  const order: SkelNode[] = [];
  const stack: SkelNode[] = [root];
  while (stack.length > 0) {
    const node = stack.pop() as SkelNode;
    order.push(node);
    for (const child of node.children) stack.push(child);
  }

  // Every child is pushed after its parent, so walking the record backwards
  // visits children before parents: post-order without a second stack.
  const inv = 1 / exponent;
  for (let i = order.length - 1; i >= 0; i -= 1) {
    const node = order[i] as SkelNode;
    const children = node.children;
    if (children.length === 0) {
      node.radius = tipRadius;
      continue;
    }
    // One child collapses to r = r_child exactly, so take it directly: the
    // pow round-trip loses a ulp per node and a long run compounds it.
    if (children.length === 1) {
      node.radius = (children[0] as SkelNode).radius;
      continue;
    }
    let sum = 0;
    for (const child of children) sum += Math.pow(child.radius, exponent);
    node.radius = Math.pow(sum, inv);
  }
}

export function trunkRadius(root: SkelNode): number {
  return root.radius;
}
