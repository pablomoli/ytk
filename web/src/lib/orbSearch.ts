// Deep-link params for /orb. theme is the filter (and the redirect target from
// /galaxy's "land" button): only a non-negative integer id survives validation.
// face picks the display typeface, while the spike compares candidates.
export const FACE_NAMES = ["instrument", "fraunces", "besley", "fell", "news"] as const;
export type FaceName = (typeof FACE_NAMES)[number];

export const validateOrbSearch = (s: Record<string, unknown>): { theme?: number; face?: FaceName } => ({
  ...(typeof s.theme === "number" && Number.isInteger(s.theme) && s.theme >= 0 ? { theme: s.theme } : {}),
  ...(FACE_NAMES.includes(s.face as FaceName) ? { face: s.face as FaceName } : {}),
});
