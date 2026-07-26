/* What to tell the user while and after pulling from the discovery sources.

   refresh_sources is synchronous — it holds the hub lock and does the network
   pulls inline — so the request being in flight really does mean "fetching
   right now". That is what makes a spinner honest here rather than decorative:
   it ends when the work ends, not when a job was merely accepted. */

export type PullResult = {
  instagram?: number;
  youtube?: number;
  pinterest?: number;
  imessage?: number;
  tiktok?: number;
  reddit?: number;
  errors?: string[];
  skipped?: boolean;
  skipped_sources?: string[];
};

const COUNTED = ["instagram", "youtube", "pinterest", "imessage", "tiktok", "reddit"] as const;

/* Named while in flight, because "loading..." for up to a minute of network
   work tells you nothing about whether it is doing what you asked. */
export function pullingLabel(only?: string[]): string {
  if (!only || only.length === 0) return "pulling all sources...";
  if (only.length === 1) return `pulling ${only[0]}...`;
  if (only.length === 2) return `pulling ${only[0]} and ${only[1]}...`;
  return `pulling ${only.length} sources...`;
}

/* A found-nothing pull and a didn't-run pull look identical from the outside
   and mean opposite things, so they get different words: the cadence skip is
   the hub declining to hammer a source, not an empty result. */
export function pullSummary(result: PullResult | undefined): string {
  if (!result) return "";
  if (result.skipped) return "skipped — pulled too recently";

  const found = COUNTED.filter((s) => (result[s] ?? 0) > 0).map((s) => `${s} +${result[s]}`);
  const errors = result.errors ?? [];

  if (found.length === 0 && errors.length > 0) return `failed — ${errors[0]}`;
  if (found.length === 0) return "nothing new";

  const summary = found.join(" · ");
  return errors.length > 0 ? `${summary} (${errors.length} failed)` : summary;
}

export function pullTotal(result: PullResult | undefined): number {
  if (!result) return 0;
  return COUNTED.reduce((n, s) => n + (result[s] ?? 0), 0);
}
