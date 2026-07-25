const ICON_PATHS: Record<string, { fill: string; d: string }> = {
  instagram: {
    fill: "#e1306c",
    d: "M7 2h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5zm0 2a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3H7zm5 3.5A4.5 4.5 0 1 1 7.5 12 4.5 4.5 0 0 1 12 7.5zm0 2A2.5 2.5 0 1 0 14.5 12 2.5 2.5 0 0 0 12 9.5zM17.6 5.4a1 1 0 1 1-1 1 1 1 0 0 1 1-1z",
  },
  tiktok: {
    fill: "#25f4ee",
    d: "M16.5 3a4.8 4.8 0 0 0 3.6 3.5V9a7.9 7.9 0 0 1-3.7-1.1v5.7a5.6 5.6 0 1 1-5.6-5.6 5 5 0 0 1 .8.06v2.6a3 3 0 1 0 2.2 2.94V3h2.7z",
  },
  youtube: {
    fill: "#ff0000",
    d: "M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C18.2 5 12 5 12 5s-6.2 0-7.8.4A2.5 2.5 0 0 0 2.4 7.2 26.3 26.3 0 0 0 2 12a26.3 26.3 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8c1.6.4 7.8.4 7.8.4s6.2 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26.3 26.3 0 0 0 22 12a26.3 26.3 0 0 0-.4-4.8zM10 15V9l5.2 3z",
  },
  pinterest: {
    fill: "#e60023",
    d: "M12 2a10 10 0 0 0-3.6 19.3c-.1-.8-.2-2 .04-2.9l1.2-5s-.3-.6-.3-1.5c0-1.4.8-2.4 1.8-2.4.9 0 1.3.6 1.3 1.4 0 .9-.6 2.2-.9 3.4-.2 1 .5 1.9 1.5 1.9 1.9 0 3.3-2 3.3-4.8 0-2.5-1.8-4.3-4.4-4.3a4.6 4.6 0 0 0-4.8 4.6c0 .9.4 1.9.8 2.4a.3.3 0 0 1 .07.3l-.3 1.2c-.05.2-.2.25-.4.15-1.3-.6-2.1-2.5-2.1-4.1 0-3.3 2.4-6.4 7-6.4 3.7 0 6.5 2.6 6.5 6.1 0 3.7-2.3 6.6-5.5 6.6-1.1 0-2.1-.6-2.4-1.2l-.7 2.5c-.2.9-.9 2-1.3 2.7A10 10 0 1 0 12 2z",
  },
  web: {
    fill: "#9ca3af",
    d: "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm7.9 9h-3a15.6 15.6 0 0 0-1.2-5.2A8 8 0 0 1 19.9 11zM12 4a13.8 13.8 0 0 1 1.9 7h-3.8A13.8 13.8 0 0 1 12 4zM8.3 5.8A15.6 15.6 0 0 0 7.1 11h-3a8 8 0 0 1 4.2-5.2zM4.1 13h3a15.6 15.6 0 0 0 1.2 5.2A8 8 0 0 1 4.1 13zM12 20a13.8 13.8 0 0 1-1.9-7h3.8A13.8 13.8 0 0 1 12 20zm3.7-1.8a15.6 15.6 0 0 0 1.2-5.2h3a8 8 0 0 1-4.2 5.2z",
  },
  memo: {
    fill: "#4ade80",
    d: "M12 15a4 4 0 0 0 4-4V6a4 4 0 1 0-8 0v5a4 4 0 0 0 4 4zm6-4a6 6 0 0 1-12 0H4a8 8 0 0 0 7 7.9V22h2v-3.1A8 8 0 0 0 20 11h-2z",
  },
};

const ICON_ALIASES: Record<string, string> = {
  "instagram-reel": "instagram",
  journal: "web",
};

/* The filterable source set — single source of truth for filter chips.
   imessage has no dedicated icon and falls back to web (by design). */
export const SOURCES = [
  "instagram",
  "youtube",
  "pinterest",
  "tiktok",
  "reddit",
  "web",
  "memo",
  "imessage",
];

/* The sources the hub can actively pull from (mirrors hub.PULL_SOURCES). A
   subset of SOURCES: `web` and `memo` are ingest types, not discovery pulls. */
export const PULL_SOURCES = ["instagram", "youtube", "pinterest", "imessage", "tiktok", "reddit"];

export function canonicalSource(source: string): string {
  return ICON_ALIASES[source] ?? source;
}

export function sourceIcon(source: string) {
  const key = canonicalSource(source);
  const icon = ICON_PATHS[key] ?? ICON_PATHS.web;
  return (
    <svg viewBox="0 0 24 24" fill={icon.fill} width="16" height="16" aria-hidden="true">
      <path d={icon.d} />
    </svg>
  );
}
