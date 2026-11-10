// Deep-link params for /orb. theme is the filter (and the redirect target from
// /galaxy's "land" button): only a non-negative integer id survives validation.
// titles picks how the sheet's titles are set, while the spike compares them.
export const SHEET_TITLES = ["shelf", "meta", "under", "scrim", "off"] as const;
export type SheetTitles = (typeof SHEET_TITLES)[number];

export const validateOrbSearch = (s: Record<string, unknown>): { theme?: number; titles?: SheetTitles } => ({
  ...(typeof s.theme === "number" && Number.isInteger(s.theme) && s.theme >= 0 ? { theme: s.theme } : {}),
  ...(SHEET_TITLES.includes(s.titles as SheetTitles) ? { titles: s.titles as SheetTitles } : {}),
});
