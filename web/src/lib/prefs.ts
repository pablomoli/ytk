/* Client-only experiment flags. Deliberately NOT in ~/.ytk/config.yaml:
   these are per-browser toggles, not system configuration. */
export const CURSOR_PREF = "ytk:cursor";
/* Whether ranked profile matches are promoted + badged in the inbox grid.
   Default off (unset): the ranking stays cached but quiet until asked for. */
export const PROFILE_MATCHES_PREF = "ytk:inbox:show-profile-matches";

/* Per-widget open state for the inbox rail. Queue and ingest default open:
   they are the common path (paste, select, ingest). */
export const RAIL_QUEUE_PREF = "ytk:inbox:rail:queue";
export const RAIL_MATCH_PREF = "ytk:inbox:rail:match";
export const RAIL_INGEST_PREF = "ytk:inbox:rail:ingest";
export const RAIL_JOB_PREF = "ytk:inbox:rail:job";

/* An unset key is not the same as an explicitly closed one: rail widgets
   need per-widget defaults, so reads take the fallback and writes record
   "0" rather than removing the key. Legacy values are "1" or absent, both
   of which still read correctly. */
export const getPref = (key: string, fallback = false): boolean => {
  try {
    const stored = localStorage.getItem(key);
    return stored === null ? fallback : stored === "1";
  } catch {
    return fallback;
  }
};

export const setPref = (key: string, on: boolean): void => {
  try {
    localStorage.setItem(key, on ? "1" : "0");
  } catch {
    /* private mode */
  }
};
