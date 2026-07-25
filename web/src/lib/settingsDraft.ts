import type { SettingsConfig, SettingsValidationError } from "../api/settings";

export function cloneSettings(config: SettingsConfig): SettingsConfig {
  return structuredClone(config);
}

export function isDirty(draft: SettingsConfig, saved: SettingsConfig): boolean {
  return JSON.stringify(draft) !== JSON.stringify(saved);
}

export function validationByPath(errors: SettingsValidationError[]): Record<string, string> {
  return Object.fromEntries(errors.map((error) => [error.loc, error.msg]));
}

export function nearestValidationPath(
  path: string,
  errors: Record<string, string>,
): string | undefined {
  return Object.keys(errors).find(
    (errorPath) => path === errorPath || errorPath.startsWith(`${path}.`),
  );
}
