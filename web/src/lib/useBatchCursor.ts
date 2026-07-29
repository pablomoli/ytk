import { useEffect, useState } from "react";
import { getStringPref, setStringPref } from "./prefs";

/* Which batch of the cached profile ranking the inbox is on, tied to the
   ranking snapshot's generated_at so a genuinely new ranking starts over
   while a refresh keeps the user's place (#138). */
export const PROFILE_BATCH_PREF = "ytk:inbox:profile-batch";

const load = (gen: string | null | undefined): number => {
  if (!gen) return 0;
  const raw = getStringPref(PROFILE_BATCH_PREF);
  if (raw === null) return 0;
  try {
    const saved: unknown = JSON.parse(raw);
    if (
      typeof saved === "object" &&
      saved !== null &&
      (saved as { gen?: unknown }).gen === gen &&
      Number.isInteger((saved as { batch?: unknown }).batch) &&
      ((saved as { batch: number }).batch) >= 0
    ) {
      return (saved as { batch: number }).batch;
    }
  } catch {
    /* garbage in storage reads as unset */
  }
  return 0;
};

/* The stored value is never clamped at write time; the clamp is derived from
   the live batchCount so a ranking that shrank cannot persist an out-of-range
   cursor, and one that grows back restores the original position. */
export function useBatchCursor(gen: string | null | undefined, batchCount: number) {
  const [batch, setBatch] = useState(() => load(gen));
  // The ranking query resolves after first render; re-hydrate when its
  // identity arrives or changes.
  useEffect(() => setBatch(load(gen)), [gen]);
  const active = Math.min(batch, Math.max(0, batchCount - 1));
  const move = (next: number) => {
    setBatch(next);
    if (gen) setStringPref(PROFILE_BATCH_PREF, JSON.stringify({ gen, batch: next }));
  };
  return {
    batch: active,
    advance: () => move((active + 1) % batchCount),
    reset: () => move(0),
  };
}
