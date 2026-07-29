// Dumps a real garden skeleton to JSON so matplotlib can plot the geometry the
// renderer actually builds, rather than a reimplementation that can drift.
import { writeFileSync } from "node:fs";
import { Vector3 } from "three";
import { growGardenTree } from "./garden/pipeline.js";
import { DEFAULT_PARAMS } from "./garden/tree.js";

const port = process.argv[2] ?? "6970";
const bucketName = process.argv[3] ?? "epicmap";
const out = process.argv[4] ?? "/tmp/skeleton.json";

const res = await fetch(`http://localhost:${port}/api/garden`);
const payload = await res.json();
const buckets = payload.buckets ?? [];
const maxNotes = Math.max(...buckets.map((b) => b.n_notes));
const bucket = buckets.find((b) => b.bucket === bucketName);
if (!bucket) throw new Error(`no bucket ${bucketName}`);

const HEIGHT_PER_REACH = 2.4;
const shape = {
  maxHeight: DEFAULT_PARAMS.reach * HEIGHT_PER_REACH,
  spreadMin: 0.35,
  spreadMax: 1.1,
  trunkFraction: 0.35,
};

const params = {
  ...DEFAULT_PARAMS,
  sagFloor: DEFAULT_PARAMS.sagFloor * shape.maxHeight * shape.trunkFraction,
};

const { root, env } = growGardenTree(
  bucket,
  maxNotes,
  shape,
  params,
  7,
  new Vector3(0, 0, 0),
  14000,
);

// Flatten to a node list with parent links so limb structure is measurable.
const nodes = [];
const stack = [{ node: root, parent: -1 }];
while (stack.length) {
  const { node, parent } = stack.pop();
  const id = nodes.length;
  nodes.push({
    id,
    parent,
    x: node.position.x,
    y: node.position.y,
    z: node.position.z,
    order: node.order,
    radius: node.radius,
    path: node.pathLength,
    kids: node.children.length,
  });
  for (const c of node.children) stack.push({ node: c, parent: id });
}

writeFileSync(
  out,
  JSON.stringify({
    bucket: bucketName,
    env: { cy: env.center.y, radius: env.radius, halfHeight: env.halfHeight },
    trunkHeight: shape.maxHeight * shape.trunkFraction,
    nodes,
  }),
);
console.log(`wrote ${out}: ${nodes.length} nodes`);
