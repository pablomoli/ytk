// Consumes /api/garden bucket snapshots (average-linkage cluster hierarchy,
// scripts/garden_lab/dendro.py). Structure is the data: cluster persistence
// ranks limb length and note mass sets lobe share, one tree per bucket. The
// generator that turns a topology into a skeleton lives in pipeline.ts.

export type TopoNode = {
  id: number;
  parent: number;
  mass: number;
  persistence: number;
  exemplars?: string[];
};
export type BucketTopology = {
  bucket: string;
  palette?: string;
  n_notes: number;
  params?: { kind: string };
  stability?: { kind: string; ari: number | null } | null;
  nodes: TopoNode[];
};
export type GardenPayload = {
  version: number;
  buckets: BucketTopology[];
  // explicit camera azimuth (radians) around the vertical axis; E7 records
  // it per stimulus so view angle is a controlled variable, not a nuisance
  azimuth?: number;
};

export async function fetchGardenPayload(): Promise<GardenPayload | null> {
  try {
    const r = await fetch("/api/garden");
    if (!r.ok) return null;
    return (await r.json()) as GardenPayload;
  } catch {
    return null;
  }
}
