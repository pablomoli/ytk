/* Where a queued item came from, read off its canonical URL.

   The queue API returns url, source, author, shared_at, text and preview_url —
   no title, domain or community. Rather than widen that payload, this derives
   the provenance a card needs from the URL it already has, which keeps the
   whole of #123 in the browser and out of the ingest path. */

export type Provenance = {
  /* Hostname without a leading www., empty when the URL will not parse. */
  domain: string;
  /* A named place within the host — r/rust, @handle — when the URL says one. */
  community?: string;
  /* What to show: the community if there is one, else the domain. Empty when
     neither is knowable, so callers can fall back to the source name. */
  label: string;
};

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function path(url: string): string[] {
  try {
    return new URL(url).pathname.split("/").filter(Boolean);
  } catch {
    return [];
  }
}

/* Only patterns where the URL genuinely names a place. A YouTube watch URL
   carries a video id, not a channel, so there is nothing to read — guessing
   one would put a wrong name on the card, which is worse than none. */
function community(domain: string, segments: string[]): string | undefined {
  if (domain.endsWith("reddit.com")) {
    const i = segments.indexOf("r");
    if (i !== -1 && segments[i + 1]) return `r/${segments[i + 1]}`;
    const u = segments.indexOf("user");
    if (u !== -1 && segments[u + 1]) return `u/${segments[u + 1]}`;
  }
  if (domain.endsWith("github.com") && segments.length >= 2) {
    return `${segments[0]}/${segments[1]}`;
  }
  if ((domain.endsWith("tiktok.com") || domain.endsWith("instagram.com")) && segments[0]?.startsWith("@")) {
    return segments[0];
  }
  return undefined;
}

/* Not every queue row points at the web. iMessage captures carry a synthetic
   "imessage:session:<hash>" identifier — 184 of 3,603 rows at the time of
   writing — and there is no original to open for those. #123 scopes the action
   to items with a canonical URL, so the link is withheld rather than rendered
   dead. */
export function isOpenable(url: string): boolean {
  try {
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

export function provenance(url: string): Provenance {
  const domain = host(url);
  const named = community(domain, path(url));
  return { domain, ...(named ? { community: named } : {}), label: named ?? domain };
}
