/* Client-only experiment flags. Deliberately NOT in ~/.ytk/config.yaml:
   these are per-browser toggles, not system configuration. */
export const CURSOR_PREF = 'ytk:cursor'

export const getPref = (key: string): boolean => {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}

export const setPref = (key: string, on: boolean): void => {
  try { on ? localStorage.setItem(key, '1') : localStorage.removeItem(key) } catch { /* private mode */ }
}
