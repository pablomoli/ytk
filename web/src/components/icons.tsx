/* Sourced glyphs carry their own viewBox rather than being rescaled by hand:
   rewriting every coordinate of a path to fit a different box is exactly the
   kind of edit that goes subtly wrong and is hard to see.

   - reddit: Simple Icons (https://simpleicons.org), CC0 for the SVG file. The
     Reddit mark itself remains Reddit's trademark; used here only to label
     Reddit's own content, which is what it is for.
   - web: Bootstrap Icons (https://icons.getbootstrap.com), MIT. */
const ICON_PATHS: Record<string, { fill: string; d: string; viewBox?: string }> = {
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
    viewBox: "0 0 16 16",
    d: "M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0M2.04 4.326c.325 1.329 2.532 2.54 3.717 3.19.48.263.793.434.743.484q-.121.12-.242.234c-.416.396-.787.749-.758 1.266.035.634.618.824 1.214 1.017.577.188 1.168.38 1.286.983.082.417-.075.988-.22 1.52-.215.782-.406 1.48.22 1.48 1.5-.5 3.798-3.186 4-5 .138-1.243-2-2-3.5-2.5-.478-.16-.755.081-.99.284-.172.15-.322.279-.51.216-.445-.148-2.5-2-1.5-2.5.78-.39.952-.171 1.227.182.078.099.163.208.273.318.609.304.662-.132.723-.633.039-.322.081-.671.277-.867.434-.434 1.265-.791 2.028-1.12.712-.306 1.365-.587 1.579-.88A7 7 0 1 1 2.04 4.327Z",
  },
  memo: {
    fill: "#4ade80",
    d: "M12 15a4 4 0 0 0 4-4V6a4 4 0 1 0-8 0v5a4 4 0 0 0 4 4zm6-4a6 6 0 0 1-12 0H4a8 8 0 0 0 7 7.9V22h2v-3.1A8 8 0 0 0 20 11h-2z",
  },
  reddit: {
    fill: "#ff4500",
    d: "M12 0C5.373 0 0 5.373 0 12c0 3.314 1.343 6.314 3.515 8.485l-2.286 2.286C.775 23.225 1.097 24 1.738 24H12c6.627 0 12-5.373 12-12S18.627 0 12 0Zm4.388 3.199c1.104 0 1.999.895 1.999 1.999 0 1.105-.895 2-1.999 2-.946 0-1.739-.657-1.947-1.539v.002c-1.147.162-2.032 1.15-2.032 2.341v.007c1.776.067 3.4.567 4.686 1.363.473-.363 1.064-.58 1.707-.58 1.547 0 2.802 1.254 2.802 2.802 0 1.117-.655 2.081-1.601 2.531-.088 3.256-3.637 5.876-7.997 5.876-4.361 0-7.905-2.617-7.998-5.87-.954-.447-1.614-1.415-1.614-2.538 0-1.548 1.255-2.802 2.803-2.802.645 0 1.239.218 1.712.585 1.275-.79 2.881-1.291 4.64-1.365v-.01c0-1.663 1.263-3.034 2.88-3.207.188-.911.993-1.595 1.959-1.595Zm-8.085 8.376c-.784 0-1.459.78-1.506 1.797-.047 1.016.64 1.429 1.426 1.429.786 0 1.371-.369 1.418-1.385.047-1.017-.553-1.841-1.338-1.841Zm7.406 0c-.786 0-1.385.824-1.338 1.841.047 1.017.634 1.385 1.418 1.385.785 0 1.473-.413 1.426-1.429-.046-1.017-.721-1.797-1.506-1.797Zm-3.703 4.013c-.974 0-1.907.048-2.77.135-.147.015-.241.168-.183.305.483 1.154 1.622 1.964 2.953 1.964 1.33 0 2.47-.81 2.953-1.964.057-.137-.037-.29-.184-.305-.863-.087-1.795-.135-2.769-.135Z",
  },
  /* imessage has no published brand glyph to source, so this is a plain speech
     bubble drawn here — a generic metaphor rather than an attempt at Apple's
     mark. It exists because the filter is icon-only (#126) and imessage
     otherwise resolved to the web globe. */
  imessage: {
    fill: "#0b93f6",
    d: "M12 4C6.9 4 3 7.1 3 11c0 2.2 1.2 4.1 3.2 5.4-.2 1.4-.9 2.7-2 3.6 1.9-.2 3.6-1 4.9-2 .9.2 1.9.3 2.9.3 5.1 0 9-3.1 9-7S17.1 4 12 4z",
  },
};

const ICON_ALIASES: Record<string, string> = {
  "instagram-reel": "instagram",
  journal: "web",
};

/* The filterable source set — single source of truth for the source filter.
   Every entry must have its own ICON_PATHS glyph: the filter shows icons only
   and reveals the name on hover, so two sources sharing a glyph are two cells
   a reader cannot tell apart. icons.test.tsx guards this. */
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

/* Which glyph a source actually resolves to, after aliases and the web
   fallback. Exported so a test can assert the SOURCES set maps to distinct
   glyphs rather than silently collapsing onto the fallback. */
export function sourceIconKey(source: string): string {
  const key = canonicalSource(source);
  return key in ICON_PATHS ? key : "web";
}

export function sourceIcon(source: string, size = 16) {
  const icon = ICON_PATHS[sourceIconKey(source)]!;
  return (
    <svg
      viewBox={icon.viewBox ?? "0 0 24 24"}
      fill={icon.fill}
      width={size}
      height={size}
      aria-hidden="true"
    >
      <path d={icon.d} />
    </svg>
  );
}
