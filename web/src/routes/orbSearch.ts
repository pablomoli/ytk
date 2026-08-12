// Deep-link filter param for /orb (and the redirect target from /galaxy's
// "land" button): only a non-negative integer theme id survives validation.
export const validateOrbSearch = (s: Record<string, unknown>) =>
  typeof s.theme === "number" && Number.isInteger(s.theme) && s.theme >= 0
    ? { theme: s.theme }
    : {};
