/* Client-only experiment flags. Deliberately NOT in ~/.ytk/config.yaml:
   these are per-browser toggles, not system configuration. */
export const CURSOR_PREF = "ytk:cursor";
/* Whether ranked profile matches are promoted + badged in the inbox grid.
   Default off (unset): the ranking stays cached but quiet until asked for. */
export const PROFILE_MATCHES_PREF = "ytk:inbox:show-profile-matches";

export const getPref = (key: string): boolean => {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
};

export const setPref = (key: string, on: boolean): void => {
  try {
    on ? localStorage.setItem(key, "1") : localStorage.removeItem(key);
  } catch {
    /* private mode */
  }
};
