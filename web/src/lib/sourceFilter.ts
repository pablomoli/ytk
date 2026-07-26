import { canonicalSource } from "../components/icons";

/* Which sources the inbox is showing (#126).

   The old filter held one optional string, so YouTube and Instagram could not
   be seen together and Reddit could not be excluded at all. This models the
   choice as a set — with one wrinkle worth stating plainly.

   `null` is not "nothing selected". It means the user has not chosen yet, and
   it resolves to everything except the sources in DEFAULT_HIDDEN. Keeping that
   as a distinct state rather than eagerly materialising a set matters because
   the list of available sources arrives with the queue data: a default computed
   at mount would be computed against an empty list and stick. An explicitly
   emptied set is a different thing again, and serializes as "none" so a reload
   cannot mistake it for "not chosen". */

export type SourceSelection = Set<string> | null;

/* Reddit is high-volume and low-signal for this queue, so it stays out until
   asked for. Excluded by policy, not by a bug — see #126. */
export const DEFAULT_HIDDEN = ["reddit"];

const EMPTY = "none";

export function parseSources(param?: string | null): SourceSelection {
  if (param === undefined || param === null || param === "") return null;
  if (param === EMPTY) return new Set<string>();
  const names = param
    .split(",")
    .map((s) => canonicalSource(s.trim().toLowerCase()))
    .filter(Boolean);
  return names.length ? new Set(names) : new Set<string>();
}

/* Sorted so the same selection always produces the same URL — otherwise two
   identical filters push two different history entries. */
export function serializeSources(selection: SourceSelection): string | undefined {
  if (selection === null) return undefined;
  if (selection.size === 0) return EMPTY;
  return [...selection].sort().join(",");
}

export function isSourceVisible(selection: SourceSelection, source: string): boolean {
  const name = canonicalSource(source);
  if (selection === null) return !DEFAULT_HIDDEN.includes(name);
  return selection.has(name);
}

/* Resolve the implicit default into a concrete set, which is what a checkbox
   list needs in order to render its boxes. */
export function materializeSources(selection: SourceSelection, available: string[]): Set<string> {
  if (selection !== null) return new Set(selection);
  return new Set(available.map(canonicalSource).filter((s) => !DEFAULT_HIDDEN.includes(s)));
}

export function toggleSource(
  selection: SourceSelection,
  source: string,
  available: string[],
): Set<string> {
  const next = materializeSources(selection, available);
  const name = canonicalSource(source);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  return next;
}

export function allSources(available: string[]): Set<string> {
  return new Set(available.map(canonicalSource));
}
